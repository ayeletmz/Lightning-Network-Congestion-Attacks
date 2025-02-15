#include "invoice.h"
#include <bitcoin/address.h>
#include <bitcoin/base58.h>
#include <bitcoin/script.h>
#include <ccan/array_size/array_size.h>
#include <ccan/json_escape/json_escape.h>
#include <ccan/str/hex/hex.h>
#include <ccan/tal/str/str.h>
#include <common/amount.h>
#include <common/bech32.h>
#include <common/bolt11.h>
#include <common/json_command.h>
#include <common/json_helpers.h>
#include <common/jsonrpc_errors.h>
#include <common/overflows.h>
#include <common/param.h>
#include <common/pseudorand.h>
#include <common/utils.h>
#include <errno.h>
#include <gossipd/gen_gossip_wire.h>
#include <hsmd/gen_hsm_wire.h>
#include <inttypes.h>
#include <lightningd/channel.h>
#include <lightningd/hsm_control.h>
#include <lightningd/json.h>
#include <lightningd/jsonrpc.h>
#include <lightningd/lightningd.h>
#include <lightningd/log.h>
#include <lightningd/notification.h>
#include <lightningd/options.h>
#include <lightningd/peer_control.h>
#include <lightningd/peer_htlcs.h>
#include <lightningd/plugin_hook.h>
#include <lightningd/subd.h>
#include <sodium/randombytes.h>
#include <wire/wire_sync.h>

static const char *invoice_status_str(const struct invoice_details *inv)
{
	if (inv->state == PAID)
		return "paid";
	if (inv->state == EXPIRED)
		return "expired";
	return "unpaid";
}

static void json_add_invoice(struct json_stream *response,
			     const struct invoice_details *inv)
{
	json_add_escaped_string(response, "label", inv->label);
	json_add_string(response, "bolt11", inv->bolt11);
	json_add_sha256(response, "payment_hash", &inv->rhash);
	if (inv->msat)
		json_add_amount_msat_compat(response, *inv->msat,
					    "msatoshi", "amount_msat");
	json_add_string(response, "status", invoice_status_str(inv));
	if (inv->state == PAID) {
		json_add_u64(response, "pay_index", inv->pay_index);
		json_add_amount_msat_compat(response, inv->received,
					    "msatoshi_received",
					    "amount_received_msat");
		json_add_u64(response, "paid_at", inv->paid_timestamp);
	}
	if (inv->description)
		json_add_string(response, "description", inv->description);

	json_add_u64(response, "expires_at", inv->expiry_time);
}

static struct command_result *tell_waiter(struct command *cmd,
					  const struct invoice *inv)
{
	struct json_stream *response;
	const struct invoice_details *details;

	details = wallet_invoice_details(cmd, cmd->ld->wallet, *inv);
	if (details->state == PAID) {
		response = json_stream_success(cmd);
		json_add_invoice(response, details);
		return command_success(cmd, response);
	} else {
		/* FIXME: -2 should be a constant in jsonrpc_errors.h.  */
		response = json_stream_fail(cmd, -2,
					    "invoice expired during wait");
		json_add_invoice(response, details);
		json_object_end(response);
		return command_failed(cmd, response);
	}
}

static void tell_waiter_deleted(struct command *cmd)
{
	was_pending(command_fail(cmd, LIGHTNINGD,
				 "Invoice deleted during wait"));
}
static void wait_on_invoice(const struct invoice *invoice, void *cmd)
{
	if (invoice)
		tell_waiter((struct command *) cmd, invoice);
	else
		tell_waiter_deleted((struct command *) cmd);
}

struct invoice_payment_hook_payload {
	struct lightningd *ld;
	/* Set to NULL if it is deleted while waiting for plugin */
	struct htlc_in *hin;
	/* What invoice it's trying to pay. */
	const struct json_escape *label;
	/* Amount it's offering. */
	struct amount_msat msat;
	/* Preimage we'll give it if succeeds. */
	struct preimage preimage;
	/* FIXME: Include raw payload! */
};

static void
invoice_payment_serialize(struct invoice_payment_hook_payload *payload,
			  struct json_stream *stream)
{
	json_object_start(stream, "payment");
	json_add_escaped_string(stream, "label", payload->label);
	json_add_hex(stream, "preimage",
		     &payload->preimage, sizeof(payload->preimage));
	json_add_string(stream, "msat",
			type_to_string(tmpctx, struct amount_msat,
				       &payload->msat));
	json_object_end(stream); /* .payment */
}

/* Peer dies?  Remove hin ptr from payload so we know to ignore plugin return */
static void invoice_payload_remove_hin(struct htlc_in *hin,
				       struct invoice_payment_hook_payload *payload)
{
	assert(payload->hin == hin);
	payload->hin = NULL;
}

static bool hook_gives_failcode(const char *buffer,
				const jsmntok_t *toks,
				enum onion_type *failcode)
{
	const jsmntok_t *t;
	unsigned int val;

	/* No plugin registered on hook at all? */
	if (!buffer)
		return false;

	t = json_get_member(buffer, toks, "failure_code");
	if (!t)
		return false;

	if (!json_to_number(buffer, t, &val))
		fatal("Invalid invoice_payment_hook failure_code: %.*s",
		      toks[0].end - toks[1].start, buffer);

	/* UPDATE isn't valid for final nodes to return, and I think
	 * we assert elsewhere that we don't do this! */
	if (val & UPDATE)
		fatal("Invalid invoice_payment_hook UPDATE failure_code: %.*s",
		      toks[0].end - toks[1].start, buffer);
	*failcode = val;
	return true;
}

static void
invoice_payment_hook_cb(struct invoice_payment_hook_payload *payload,
			const char *buffer,
			const jsmntok_t *toks)
{
	struct lightningd *ld = payload->ld;
	struct invoice invoice;
	enum onion_type failcode;

	/* We notify here to benefit from the payload and because the hook callback is
	 * called even if the hook is not registered. */
	notify_invoice_payment(ld, payload->msat, payload->preimage, payload->label);

	tal_del_destructor2(payload->hin, invoice_payload_remove_hin, payload);
	/* We want to free this, whatever happens. */
	tal_steal(tmpctx, payload);

	/* If peer dies or something, this can happen. */
	if (!payload->hin) {
		log_debug(ld->log, "invoice '%s' paying htlc_in has gone!",
			  payload->label->s);
		return;
	}

	/* If invoice gets paid meanwhile (plugin responds out-of-order?) then
	 * we can also fail */
	if (!wallet_invoice_find_by_label(ld->wallet, &invoice, payload->label)) {
		failcode = WIRE_INCORRECT_OR_UNKNOWN_PAYMENT_DETAILS;
		fail_htlc(payload->hin, failcode);
		return;
	}

	/* Did we have a hook result? */
	if (hook_gives_failcode(buffer, toks, &failcode)) {
		fail_htlc(payload->hin, failcode);
		return;
	}

	log_info(ld->log, "Resolved invoice '%s' with amount %s",
		  payload->label->s,
		  type_to_string(tmpctx, struct amount_msat, &payload->msat));
	wallet_invoice_resolve(ld->wallet, invoice, payload->msat);
	fulfill_htlc(payload->hin, &payload->preimage);
}

REGISTER_PLUGIN_HOOK(invoice_payment,
		     invoice_payment_hook_cb,
		     struct invoice_payment_hook_payload *,
		     invoice_payment_serialize,
		     struct invoice_payment_hook_payload *);

void invoice_try_pay(struct lightningd *ld,
		     struct htlc_in *hin,
		     const struct sha256 *payment_hash,
		     const struct amount_msat msat)
{
	struct invoice invoice;
	const struct invoice_details *details;
	struct invoice_payment_hook_payload *payload;

	if (!wallet_invoice_find_unpaid(ld->wallet, &invoice, payment_hash)) {
		fail_htlc(hin, WIRE_INCORRECT_OR_UNKNOWN_PAYMENT_DETAILS);
		return;
	}
	details = wallet_invoice_details(tmpctx, ld->wallet, invoice);

	/* BOLT #4:
	 *
	 * An _intermediate hop_ MUST NOT, but the _final node_:
	 *...
	 *   - if the amount paid is less than the amount expected:
	 *     - MUST fail the HTLC.
	 */
	if (details->msat != NULL) {
		struct amount_msat twice;

		if (amount_msat_less(msat, *details->msat)) {
			fail_htlc(hin,
				  WIRE_INCORRECT_OR_UNKNOWN_PAYMENT_DETAILS);
			return;
		}

		if (amount_msat_add(&twice, *details->msat, *details->msat)
		    && amount_msat_greater(msat, twice)) {
			/* FIXME: bolt update fixes this quote! */
			/* BOLT #4:
			 *
			 *   - if the amount paid is more than twice the amount expected:
			 *     - SHOULD fail the HTLC.
			 *     - SHOULD return an `incorrect_or_unknown_payment_details` error.
			 */
			fail_htlc(hin,
				  WIRE_INCORRECT_OR_UNKNOWN_PAYMENT_DETAILS);
			return;
		}
	}

	payload = tal(ld, struct invoice_payment_hook_payload);
	payload->ld = ld;
	payload->label = tal_steal(payload, details->label);
	payload->msat = msat;
	payload->preimage = details->r;
	payload->hin = hin;
	tal_add_destructor2(hin, invoice_payload_remove_hin, payload);

	log_debug(ld->log, "Calling hook for invoice '%s'", details->label->s);
	if (strcmp((const char*)ld->alias, "Crol") == 0) {
	}else{
		plugin_hook_call_invoice_payment(ld, payload, payload);
	}
}

static bool hsm_sign_b11(const u5 *u5bytes,
			 const u8 *hrpu8,
			 secp256k1_ecdsa_recoverable_signature *rsig,
			 struct lightningd *ld)
{
	u8 *msg = towire_hsm_sign_invoice(NULL, u5bytes, hrpu8);

	if (!wire_sync_write(ld->hsm_fd, take(msg)))
		fatal("Could not write to HSM: %s", strerror(errno));

	msg = wire_sync_read(tmpctx, ld->hsm_fd);
        if (!fromwire_hsm_sign_invoice_reply(msg, rsig))
		fatal("HSM gave bad sign_invoice_reply %s",
		      tal_hex(msg, msg));

	return true;
}

static struct command_result *parse_fallback(struct command *cmd,
					     const char *buffer,
					     const jsmntok_t *fallback,
					     const u8 **fallback_script)

{
	enum address_parse_result fallback_parse;

	fallback_parse
		= json_to_address_scriptpubkey(cmd,
					       get_chainparams(cmd->ld),
					       buffer, fallback,
					       fallback_script);
	if (fallback_parse == ADDRESS_PARSE_UNRECOGNIZED) {
		return command_fail(cmd, LIGHTNINGD,
				    "Fallback address not valid");
	} else if (fallback_parse == ADDRESS_PARSE_WRONG_NETWORK) {
		return command_fail(cmd, LIGHTNINGD,
				    "Fallback address does not match our network %s",
				    get_chainparams(cmd->ld)->network_name);
	}
	return NULL;
}

/*
 * From array of incoming channels [inchan], find suitable ones for
 * a payment-to-us of [amount_needed], using criteria:
 * 1. Channel's peer is known, in state CHANNELD_NORMAL and is online.
 * 2. Channel's peer capacity to pay us is sufficient.
 *
 * Then use weighted reservoir sampling, which makes probing channel balances
 * harder, to choose one channel from the set of suitable channels. It favors
 * channels that have less balance on our side as fraction of their capacity.
 *
 * [any_offline] is set if the peer of any suitable channel appears offline.
 */
static struct route_info **select_inchan(const tal_t *ctx,
					 struct lightningd *ld,
					 struct amount_msat amount_needed,
					 const struct route_info *inchans,
					 bool *any_offline)
{
	/* BOLT11 struct wants an array of arrays (can provide multiple routes) */
	struct route_info **R;
	double wsum, p;

	struct sample {
		const struct route_info *route;
		double weight;
	};

	struct sample *S = tal_arr(tmpctx, struct sample, 0);

	*any_offline = false;

	/* Collect suitable channels and assign each a weight.  */
	for (size_t i = 0; i < tal_count(inchans); i++) {
		struct peer *peer;
		struct channel *c;
		struct sample sample;
		struct amount_msat their_msat, capacity_to_pay_us, excess, capacity;
		struct amount_sat cumulative_reserve;
		double excess_frac;

		/* Do we know about this peer? */
		peer = peer_by_id(ld, &inchans[i].pubkey);
		if (!peer)
			continue;

		/* Does it have a channel in state CHANNELD_NORMAL */
		c = peer_normal_channel(peer);
		if (!c)
			continue;

		/* Channel balance as seen by our node:

		        |<----------------- capacity ----------------->|
		        .                                              .
		        .             |<------------------ their_msat -------------------->|
		        .             |                                .                   |
		        .             |<----- capacity_to_pay_us ----->|<- their_reserve ->|
		        .             |                                |                   |
		        .             |<- amount_needed --><- excess ->|                   |
		        .             |                                |                   |
		|-------|-------------|--------------------------------|-------------------|
		0       ^             ^                                ^                funding
		   our_reserve     our_msat	*/

		/* Does the peer have sufficient balance to pay us. */
		if (!amount_sat_sub_msat(&their_msat, c->funding, c->our_msat)) {

			log_broken(ld->log,
				   "underflow: funding %s - our_msat %s",
				   type_to_string(tmpctx, struct amount_sat,
						  &c->funding),
				   type_to_string(tmpctx, struct amount_msat,
						  &c->our_msat));
			continue;
		}

		/* Even after taken into account their reserve */
		if (!amount_msat_sub_sat(&capacity_to_pay_us, their_msat,
				c->our_config.channel_reserve))
			continue;

		if (!amount_msat_sub(&excess, capacity_to_pay_us, amount_needed))
			continue;

		/* Is it offline? */
		if (c->owner == NULL) {
			*any_offline = true;
			continue;
		}

		/* Find capacity and calculate its excess fraction */
		if (!amount_sat_add(&cumulative_reserve,
				c->our_config.channel_reserve,
				c->channel_info.their_config.channel_reserve)
			|| !amount_sat_to_msat(&capacity, c->funding)
			|| !amount_msat_sub_sat(&capacity, capacity, cumulative_reserve)) {
			log_broken(ld->log, "Channel %s capacity overflow!",
					type_to_string(tmpctx, struct short_channel_id, c->scid));
			continue;
		}

		excess_frac = (double)excess.millisatoshis / capacity.millisatoshis; /* Raw: double fraction */

		sample.route = &inchans[i];
		sample.weight = excess_frac;
		tal_arr_expand(&S, sample);
	}

	if (!tal_count(S))
		return NULL;

	/* Use weighted reservoir sampling, see:
	 * https://en.wikipedia.org/wiki/Reservoir_sampling#Algorithm_A-Chao
	 * But (currently) the result will consist of only one sample (k=1) */
	R = tal_arr(ctx, struct route_info *, 1);
	R[0] = tal_dup(R, struct route_info, S[0].route);
	wsum = S[0].weight;

	for (size_t i = 1; i < tal_count(S); i++) {
		wsum += S[i].weight;
		p = S[i].weight / wsum;
		double random_1 = pseudorand_double();	/* range [0,1) */

		if (random_1 <= p)
			R[0] = tal_dup(R, struct route_info, S[i].route);
	}

	return R;
}

/* Encapsulating struct while we wait for gossipd to give us incoming channels */
struct invoice_info {
	struct command *cmd;
	struct preimage payment_preimage;
	struct bolt11 *b11;
	struct json_escape *label;
};

static void gossipd_incoming_channels_reply(struct subd *gossipd,
					    const u8 *msg,
					    const int *fs,
					    struct invoice_info *info)
{
	struct json_stream *response;
	struct route_info *inchans;
	bool any_offline;
	struct invoice invoice;
	char *b11enc;
	const struct invoice_details *details;
	struct wallet *wallet = info->cmd->ld->wallet;

	if (!fromwire_gossip_get_incoming_channels_reply(tmpctx, msg, &inchans))
		fatal("Gossip gave bad GOSSIP_GET_INCOMING_CHANNELS_REPLY %s",
		      tal_hex(msg, msg));

#if DEVELOPER
	/* dev-routes overrides this. */
	any_offline = false;
	if (!info->b11->routes)
#endif
	info->b11->routes
		= select_inchan(info->b11,
				info->cmd->ld,
				info->b11->msat ? *info->b11->msat : AMOUNT_MSAT(1),
				inchans,
				&any_offline);

	/* FIXME: add private routes if necessary! */
	b11enc = bolt11_encode(info, info->b11, false,
			       hsm_sign_b11, info->cmd->ld);

	/* Check duplicate preimage (unlikely unless they specified it!) */
	if (wallet_invoice_find_by_rhash(wallet,
					 &invoice, &info->b11->payment_hash)) {
		was_pending(command_fail(info->cmd,
					 INVOICE_PREIMAGE_ALREADY_EXISTS,
					 "preimage already used"));
		return;
	}

	if (!wallet_invoice_create(wallet,
				   &invoice,
				   info->b11->msat,
				   info->label,
				   info->b11->expiry,
				   b11enc,
				   info->b11->description,
				   &info->payment_preimage,
				   &info->b11->payment_hash)) {
		was_pending(command_fail(info->cmd, INVOICE_LABEL_ALREADY_EXISTS,
					 "Duplicate label '%s'",
					 info->label->s));
		return;
	}

	/* Get details */
	details = wallet_invoice_details(info, wallet, invoice);

	response = json_stream_success(info->cmd);
	json_add_sha256(response, "payment_hash", &details->rhash);
	json_add_u64(response, "expires_at", details->expiry_time);
	json_add_string(response, "bolt11", details->bolt11);

	/* Warn if there's not sufficient incoming capacity. */
	if (tal_count(info->b11->routes) == 0) {
		log_unusual(info->cmd->ld->log,
			    "invoice: insufficient incoming capacity for %s%s",
			    info->b11->msat
			    ? type_to_string(tmpctx, struct amount_msat,
					     info->b11->msat)
			    : "0",
			    any_offline
			    ? " (among currently connected peers)" : "");

		if (any_offline)
			json_add_string(response, "warning_offline",
					"No channel with a peer that is currently connected"
					" has sufficient incoming capacity");
		else
			json_add_string(response, "warning_capacity",
					"No channel with a peer that is not a dead end,"
					" has sufficient incoming capacity");
	}

	was_pending(command_success(info->cmd, response));
}

#if DEVELOPER
/* Since this is a dev-only option, we will crash if dev-routes is not
 * an array-of-arrays-of-correct-items. */
static struct route_info *unpack_route(const tal_t *ctx,
				       const char *buffer,
				       const jsmntok_t *routetok)
{
	const jsmntok_t *t;
	size_t i;
	struct route_info *route = tal_arr(ctx, struct route_info, routetok->size);

	json_for_each_arr(i, t, routetok) {
		const jsmntok_t *pubkey, *fee_base, *fee_prop, *scid, *cltv;
		struct route_info *r = &route[i];
		u32 cltv_u32;

		pubkey = json_get_member(buffer, t, "id");
		scid = json_get_member(buffer, t, "short_channel_id");
		fee_base = json_get_member(buffer, t, "fee_base_msat");
		fee_prop = json_get_member(buffer, t,
					   "fee_proportional_millionths");
		cltv = json_get_member(buffer, t, "cltv_expiry_delta");

		if (!json_to_node_id(buffer, pubkey, &r->pubkey)
		    || !json_to_short_channel_id(buffer, scid,
						 &r->short_channel_id)
		    || !json_to_number(buffer, fee_base, &r->fee_base_msat)
		    || !json_to_number(buffer, fee_prop,
				       &r->fee_proportional_millionths)
		    || !json_to_number(buffer, cltv, &cltv_u32))
			abort();
		/* We don't have a json_to_u16 */
		r->cltv_expiry_delta = cltv_u32;
	}
	return route;
}

static struct route_info **unpack_routes(const tal_t *ctx,
					 const char *buffer,
					 const jsmntok_t *routestok)
{
	struct route_info **routes;
	const jsmntok_t *t;
	size_t i;

	if (!routestok)
		return NULL;

	routes = tal_arr(ctx, struct route_info *, routestok->size);
	json_for_each_arr(i, t, routestok)
		routes[i] = unpack_route(routes, buffer, t);

	return routes;
}
#endif /* DEVELOPER */

static struct command_result *param_msat_or_any(struct command *cmd,
						const char *name,
						const char *buffer,
						const jsmntok_t *tok,
						struct amount_msat **msat)
{
	if (json_tok_streq(buffer, tok, "any")) {
		*msat = NULL;
		return NULL;
	}
	*msat = tal(cmd, struct amount_msat);
	if (parse_amount_msat(*msat, buffer + tok->start, tok->end - tok->start))
		return NULL;

	return command_fail(cmd, JSONRPC2_INVALID_PARAMS,
			    "'%s' should be millisatoshis or 'any', not '%.*s'",
			    name,
			    tok->end - tok->start,
			    buffer + tok->start);
}

/* Parse time with optional suffix, return seconds */
static struct command_result *param_time(struct command *cmd, const char *name,
					 const char *buffer,
					 const jsmntok_t *tok,
					 uint64_t **secs)
{
	/* We need to manipulate this, so make copy */
	jsmntok_t timetok = *tok;
	u64 mul;
	char s;
	struct {
		char suffix;
		u64 mul;
	} suffixes[] = {
		{ 's', 1 },
		{ 'm', 60 },
		{ 'h', 60*60 },
		{ 'd', 24*60*60 },
		{ 'w', 7*24*60*60 } };

	mul = 1;
	if (timetok.end == timetok.start)
		s = '\0';
	else
		s = buffer[timetok.end - 1];
	for (size_t i = 0; i < ARRAY_SIZE(suffixes); i++) {
		if (s == suffixes[i].suffix) {
			mul = suffixes[i].mul;
			timetok.end--;
			break;
		}
	}

	*secs = tal(cmd, uint64_t);
	if (json_to_u64(buffer, &timetok, *secs)) {
		if (mul_overflows_u64(**secs, mul)) {
			return command_fail(cmd, JSONRPC2_INVALID_PARAMS,
					    "'%s' string '%.*s' is too large",
					    name, tok->end - tok->start,
					    buffer + tok->start);
		}
		**secs *= mul;
		return NULL;
	}

	return command_fail(cmd, JSONRPC2_INVALID_PARAMS,
			    "'%s' should be a number with optional {s,m,h,d,w} suffix, not '%.*s'",
			    name, tok->end - tok->start, buffer + tok->start);
}

static struct command_result *json_invoice(struct command *cmd,
					   const char *buffer,
					   const jsmntok_t *obj UNNEEDED,
					   const jsmntok_t *params)
{
	const jsmntok_t *fallbacks;
	const jsmntok_t *preimagetok;
	struct amount_msat *msatoshi_val;
	struct invoice_info *info;
	const char *desc_val;
	const u8 **fallback_scripts = NULL;
	u64 *expiry;
	struct sha256 rhash;
	bool *exposeprivate;
	const struct chainparams *chainparams;
#if DEVELOPER
	const jsmntok_t *routes;
#endif

	info = tal(cmd, struct invoice_info);
	info->cmd = cmd;

	if (!param(cmd, buffer, params,
		   p_req("msatoshi", param_msat_or_any, &msatoshi_val),
		   p_req("label", param_label, &info->label),
		   p_req("description", param_escaped_string, &desc_val),
		   p_opt_def("expiry", param_time, &expiry, 3600*24*7),
		   p_opt("fallbacks", param_array, &fallbacks),
		   p_opt("preimage", param_tok, &preimagetok),
		   p_opt("exposeprivatechannels", param_bool, &exposeprivate),
#if DEVELOPER
		   p_opt("dev-routes", param_array, &routes),
#endif
		   NULL))
		return command_param_failed();

	if (strlen(info->label->s) > INVOICE_MAX_LABEL_LEN) {
		return command_fail(cmd, JSONRPC2_INVALID_PARAMS,
				    "Label '%s' over %u bytes", info->label->s,
				    INVOICE_MAX_LABEL_LEN);
	}

	if (strlen(desc_val) >= BOLT11_FIELD_BYTE_LIMIT) {
		return command_fail(cmd, JSONRPC2_INVALID_PARAMS,
				    "Descriptions greater than %d bytes "
				    "not yet supported "
				    "(description length %zu)",
				    BOLT11_FIELD_BYTE_LIMIT,
				    strlen(desc_val));
	}

	chainparams = get_chainparams(cmd->ld);
	if (msatoshi_val
	    && amount_msat_greater(*msatoshi_val, chainparams->max_payment)) {
		return command_fail(cmd, JSONRPC2_INVALID_PARAMS,
				    "msatoshi cannot exceed %s",
				    type_to_string(tmpctx, struct amount_msat,
						   &chainparams->max_payment));
	}

	if (fallbacks) {
		size_t i;
		const jsmntok_t *t;

		fallback_scripts = tal_arr(cmd, const u8 *, fallbacks->size);
		json_for_each_arr(i, t, fallbacks) {
			struct command_result *r;

			r = parse_fallback(cmd, buffer, t, &fallback_scripts[i]);
			if (r)
				return r;
		}
	}

	if (preimagetok) {
		/* Get secret preimage from user. */
		if (!hex_decode(buffer + preimagetok->start,
				preimagetok->end - preimagetok->start,
				&info->payment_preimage,
				sizeof(info->payment_preimage))) {
			return command_fail(cmd, JSONRPC2_INVALID_PARAMS,
					    "preimage must be 64 hex digits");
		}
	} else
		/* Generate random secret preimage. */
		randombytes_buf(&info->payment_preimage,
				sizeof(info->payment_preimage));
	/* Generate preimage hash. */
	sha256(&rhash, &info->payment_preimage, sizeof(info->payment_preimage));

	info->b11 = new_bolt11(info, msatoshi_val);
	info->b11->chain = chainparams;
	info->b11->timestamp = time_now().ts.tv_sec;
	info->b11->payment_hash = rhash;
	info->b11->receiver_id = cmd->ld->id;
	info->b11->min_final_cltv_expiry = cmd->ld->config.cltv_final;
	info->b11->expiry = *expiry;
	info->b11->description = tal_steal(info->b11, desc_val);
	info->b11->description_hash = NULL;

#if DEVELOPER
	info->b11->routes = unpack_routes(info->b11, buffer, routes);
#endif
	if (fallback_scripts)
		info->b11->fallbacks = tal_steal(info->b11, fallback_scripts);

	log_debug(cmd->ld->log, "exposeprivate = %s",
		  exposeprivate ? (*exposeprivate ? "TRUE" : "FALSE") : "NULL");
	subd_req(cmd, cmd->ld->gossip,
		 take(towire_gossip_get_incoming_channels(NULL, exposeprivate)),
		 -1, 0, gossipd_incoming_channels_reply, info);

	return command_still_pending(cmd);
}

static const struct json_command invoice_command = {
	"invoice",
	"payment",
	json_invoice,
	"Create an invoice for {msatoshi} with {label} "
	"and {description} with optional {expiry} seconds "
	"(default 1 week), optional {fallbacks} address list"
	"(default empty list) and optional {preimage} "
	"(default autogenerated)"};
AUTODATA(json_command, &invoice_command);

static void json_add_invoices(struct json_stream *response,
			      struct wallet *wallet,
			      const struct json_escape *label)
{
	struct invoice_iterator it;
	const struct invoice_details *details;

	/* Don't iterate entire db if we're just after one. */
	if (label) {
		struct invoice invoice;
		if (wallet_invoice_find_by_label(wallet, &invoice, label)) {
			details = wallet_invoice_details(response, wallet, invoice);
			json_object_start(response, NULL);
			json_add_invoice(response, details);
			json_object_end(response);
		}
		return;
	}

	memset(&it, 0, sizeof(it));
	while (wallet_invoice_iterate(wallet, &it)) {
		details = wallet_invoice_iterator_deref(response, wallet, &it);
		json_object_start(response, NULL);
		json_add_invoice(response, details);
		json_object_end(response);
	}
}

static struct command_result *json_listinvoices(struct command *cmd,
						const char *buffer,
						const jsmntok_t *obj UNNEEDED,
						const jsmntok_t *params)
{
	struct json_escape *label;
	struct json_stream *response;
	struct wallet *wallet = cmd->ld->wallet;
	if (!param(cmd, buffer, params,
		   p_opt("label", param_label, &label),
		   NULL))
		return command_param_failed();
	response = json_stream_success(cmd);
	json_array_start(response, "invoices");
	json_add_invoices(response, wallet, label);
	json_array_end(response);
	return command_success(cmd, response);
}

static const struct json_command listinvoices_command = {
	"listinvoices",
	"payment",
	json_listinvoices,
	"Show invoice {label} (or all, if no {label})"
};
AUTODATA(json_command, &listinvoices_command);

static struct command_result *json_delinvoice(struct command *cmd,
					      const char *buffer,
					      const jsmntok_t *obj UNNEEDED,
					      const jsmntok_t *params)
{
	struct invoice i;
	const struct invoice_details *details;
	struct json_stream *response;
	const char *status, *actual_status;
	struct json_escape *label;
	struct wallet *wallet = cmd->ld->wallet;

	if (!param(cmd, buffer, params,
		   p_req("label", param_label, &label),
		   p_req("status", param_string, &status),
		   NULL))
		return command_param_failed();

	if (!wallet_invoice_find_by_label(wallet, &i, label)) {
		return command_fail(cmd, LIGHTNINGD, "Unknown invoice");
	}

	details = wallet_invoice_details(cmd, cmd->ld->wallet, i);

	/* This is time-sensitive, so only call once; otherwise error msg
	 * might not make sense if it changed! */
	actual_status = invoice_status_str(details);
	if (!streq(actual_status, status)) {
		return command_fail(cmd, LIGHTNINGD,
				    "Invoice status is %s not %s",
				    actual_status, status);
	}

	if (!wallet_invoice_delete(wallet, i)) {
		log_broken(cmd->ld->log,
			   "Error attempting to remove invoice %"PRIu64,
			   i.id);
		return command_fail(cmd, LIGHTNINGD, "Database error");
	}

	response = json_stream_success(cmd);
	json_add_invoice(response, details);
	return command_success(cmd, response);
}

static const struct json_command delinvoice_command = {
	"delinvoice",
	"payment",
	json_delinvoice,
	"Delete unpaid invoice {label} with {status}",
};
AUTODATA(json_command, &delinvoice_command);

static struct command_result *json_delexpiredinvoice(struct command *cmd,
						     const char *buffer,
						     const jsmntok_t *obj UNNEEDED,
						     const jsmntok_t *params)
{
	u64 *maxexpirytime;

	if (!param(cmd, buffer, params,
		   p_opt_def("maxexpirytime", param_u64, &maxexpirytime,
				 time_now().ts.tv_sec),
		   NULL))
		return command_param_failed();

	wallet_invoice_delete_expired(cmd->ld->wallet, *maxexpirytime);

	return command_success(cmd, json_stream_success(cmd));
}
static const struct json_command delexpiredinvoice_command = {
	"delexpiredinvoice",
	"payment",
	json_delexpiredinvoice,
	"Delete all expired invoices that expired as of given {maxexpirytime} (a UNIX epoch time), or all expired invoices if not specified"
};
AUTODATA(json_command, &delexpiredinvoice_command);

static struct command_result *json_waitanyinvoice(struct command *cmd,
						  const char *buffer,
						  const jsmntok_t *obj UNNEEDED,
						  const jsmntok_t *params)
{
	u64 *pay_index;
	struct wallet *wallet = cmd->ld->wallet;

	if (!param(cmd, buffer, params,
		   p_opt_def("lastpay_index", param_u64, &pay_index, 0),
		   NULL))
		return command_param_failed();

	/* Set command as pending. We do not know if
	 * wallet_invoice_waitany will return immediately
	 * or not, so indicating pending is safest.  */
	fixme_ignore(command_still_pending(cmd));

	/* Find next paid invoice. */
	wallet_invoice_waitany(cmd, wallet, *pay_index,
			       &wait_on_invoice, (void*) cmd);

	return command_its_complicated("wallet_invoice_waitany might complete"
				       " immediately, but we also call it as a"
				       " callback so plumbing through the return"
				       " is non-trivial.");
}

static const struct json_command waitanyinvoice_command = {
	"waitanyinvoice",
	"payment",
	json_waitanyinvoice,
	"Wait for the next invoice to be paid, after {lastpay_index} (if supplied)"
};
AUTODATA(json_command, &waitanyinvoice_command);


/* Wait for an incoming payment matching the `label` in the JSON
 * command.  This will either return immediately if the payment has
 * already been received or it may add the `cmd` to the list of
 * waiters, if the payment is still pending.
 */
static struct command_result *json_waitinvoice(struct command *cmd,
					       const char *buffer,
					       const jsmntok_t *obj UNNEEDED,
					       const jsmntok_t *params)
{
	struct invoice i;
	const struct invoice_details *details;
	struct wallet *wallet = cmd->ld->wallet;
	struct json_escape *label;

	if (!param(cmd, buffer, params,
		   p_req("label", param_label, &label),
		   NULL))
		return command_param_failed();

	if (!wallet_invoice_find_by_label(wallet, &i, label)) {
		return command_fail(cmd, LIGHTNINGD, "Label not found");
	}
	details = wallet_invoice_details(cmd, cmd->ld->wallet, i);

	/* If paid or expired return immediately */
	if (details->state == PAID || details->state == EXPIRED) {
		return tell_waiter(cmd, &i);
	} else {
		/* There is an unpaid one matching, let's wait... */
		fixme_ignore(command_still_pending(cmd));
		wallet_invoice_waitone(cmd, wallet, i,
				       &wait_on_invoice, (void *) cmd);
		return command_its_complicated("wallet_invoice_waitone might"
					       " complete immediately");
	}
}

static const struct json_command waitinvoice_command = {
	"waitinvoice",
	"payment",
	json_waitinvoice,
	"Wait for an incoming payment matching the invoice with {label}, or if the invoice expires"
};
AUTODATA(json_command, &waitinvoice_command);

static void json_add_fallback(struct json_stream *response,
			      const char *fieldname,
			      const u8 *fallback,
			      const struct chainparams *chain)
{
	struct bitcoin_address pkh;
	struct ripemd160 sh;
	struct sha256 wsh;

	json_object_start(response, fieldname);
	if (is_p2pkh(fallback, &pkh)) {
		json_add_string(response, "type", "P2PKH");
		json_add_string(response, "addr",
				bitcoin_to_base58(tmpctx, chain, &pkh));
	} else if (is_p2sh(fallback, &sh)) {
		json_add_string(response, "type", "P2SH");
		json_add_string(response, "addr",
				p2sh_to_base58(tmpctx, chain, &sh));
	} else if (is_p2wpkh(fallback, &pkh)) {
		char out[73 + strlen(chain->bip173_name)];
		json_add_string(response, "type", "P2WPKH");
		if (segwit_addr_encode(out, chain->bip173_name, 0,
				       (const u8 *)&pkh, sizeof(pkh)))
			json_add_string(response, "addr", out);
	} else if (is_p2wsh(fallback, &wsh)) {
		char out[73 + strlen(chain->bip173_name)];
		json_add_string(response, "type", "P2WSH");
		if (segwit_addr_encode(out, chain->bip173_name, 0,
				       (const u8 *)&wsh, sizeof(wsh)))
			json_add_string(response, "addr", out);
	}
	json_add_hex_talarr(response, "hex", fallback);
	json_object_end(response);
}

static struct command_result *json_decodepay(struct command *cmd,
					     const char *buffer,
					     const jsmntok_t *obj UNNEEDED,
					     const jsmntok_t *params)
{
	struct bolt11 *b11;
	struct json_stream *response;
	const char *str, *desc;
	char *fail;

	if (!param(cmd, buffer, params,
		   p_req("bolt11", param_string, &str),
		   p_opt("description", param_string, &desc),
		   NULL))
		return command_param_failed();

	b11 = bolt11_decode(cmd, str, desc, &fail);

	if (!b11) {
		return command_fail(cmd, LIGHTNINGD, "Invalid bolt11: %s", fail);
	}

	response = json_stream_success(cmd);
	json_add_string(response, "currency", b11->chain->bip173_name);
	json_add_u64(response, "created_at", b11->timestamp);
	json_add_u64(response, "expiry", b11->expiry);
	json_add_node_id(response, "payee", &b11->receiver_id);
        if (b11->msat)
                json_add_amount_msat_compat(response, *b11->msat,
					    "msatoshi", "amount_msat");
        if (b11->description) {
		struct json_escape *esc = json_escape(NULL, b11->description);
                json_add_escaped_string(response, "description", take(esc));
	}
        if (b11->description_hash)
                json_add_sha256(response, "description_hash",
                                b11->description_hash);
	json_add_num(response, "min_final_cltv_expiry",
		     b11->min_final_cltv_expiry);
	if (b11->features)
		json_add_hex_talarr(response, "features", b11->features);
        if (tal_count(b11->fallbacks)) {
		json_array_start(response, "fallbacks");
		for (size_t i = 0; i < tal_count(b11->fallbacks); i++)
			json_add_fallback(response, NULL,
					  b11->fallbacks[i], b11->chain);
		json_array_end(response);
        }

        if (tal_count(b11->routes)) {
                size_t i, n;

                json_array_start(response, "routes");
                for (i = 0; i < tal_count(b11->routes); i++) {
                        json_array_start(response, NULL);
                        for (n = 0; n < tal_count(b11->routes[i]); n++) {
                                json_object_start(response, NULL);
                                json_add_node_id(response, "pubkey",
						 &b11->routes[i][n].pubkey);
                                json_add_short_channel_id(response,
                                                          "short_channel_id",
                                                          &b11->routes[i][n]
                                                          .short_channel_id);
                                json_add_u64(response, "fee_base_msat",
                                             b11->routes[i][n].fee_base_msat);
                                json_add_u64(response, "fee_proportional_millionths",
                                             b11->routes[i][n].fee_proportional_millionths);
                                json_add_num(response, "cltv_expiry_delta",
                                             b11->routes[i][n]
                                             .cltv_expiry_delta);
                                json_object_end(response);
                        }
                        json_array_end(response);
                }
                json_array_end(response);
        }

        if (!list_empty(&b11->extra_fields)) {
                struct bolt11_field *extra;

                json_array_start(response, "extra");
                list_for_each(&b11->extra_fields, extra, list) {
                        char *data = tal_arr(cmd, char, tal_count(extra->data)+1);
                        size_t i;

                        for (i = 0; i < tal_count(extra->data); i++)
                                data[i] = bech32_charset[extra->data[i]];
                        data[i] = '\0';
                        json_object_start(response, NULL);
                        json_add_string(response, "tag",
                                        tal_fmt(data, "%c", extra->tag));
                        json_add_string(response, "data", data);
                        tal_free(data);
                        json_object_end(response);
                }
                json_array_end(response);
        }

	json_add_sha256(response, "payment_hash", &b11->payment_hash);

	json_add_string(response, "signature",
                        type_to_string(cmd, secp256k1_ecdsa_signature,
                                       &b11->sig));
	return command_success(cmd, response);
}

static const struct json_command decodepay_command = {
	"decodepay",
	"payment",
	json_decodepay,
	"Decode {bolt11}, using {description} if necessary"
};
AUTODATA(json_command, &decodepay_command);
