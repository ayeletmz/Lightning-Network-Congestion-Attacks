#!/bin/bash

# actors: Alice, Bob
# channels: Bob->Alice->Bob
# Use case: Normal (Everyone return secret), route back and forth on Alice<->Bob channel.
# We wish to verify that the maximum route length is 20 (in the meaning of 20 steps).

HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp11_max_20_hops_$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=100

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file


create_channel Bob Alice $Alice_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Bob


alice_id=''
get_node_id Alice alice_id
Bob_id=''
get_node_id Bob bob_id
sleep 2s

edebug "number of blocks: $(bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount)" |& tee -a $log_file

#### Phase 1: Bob pays Alice #####

einfo "\n####### Phase 1: Bob pays Alice #######" |& tee -a $log_file

print_channel_balances Bob Alice

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc invoice 2000000000 "Alice_to_Bob-$(date +'%T:%N')" "$(date +'%T:%N') tx of 200000000 msat from Alice to Bob")

einfo "$inv" |& tee -a $log_file

bolt11=$(jq '.bolt11' <<< "$inv")

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc pay $bolt11

print_channel_balances Bob Alice

#### Phase 2: Bob pays himself #####

einfo "\n####### Phase 2: Bob transfers money to himself through the lightning channel back and forth through Alice #######" |& tee -a $log_file


edebug "\npayment iteration $iteration" |& tee -a $log_file

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc invoice $payment_amount "a-$(date +'%T:%N') $iteration" "$(date +'%T:%N') tx of $payment_amount msat a $iteration")

einfo "$inv" |& tee -a $log_file

payment_hash=$(jq '.payment_hash' <<< "$inv")

route="[
 {
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+20)),
	\"amount_msat\" : \"$((payment_amount+20))msat\",
	\"delay\" : 129
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+19)),
	\"amount_msat\" : \"$((payment_amount+19))msat\",
	\"delay\" : 123
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+18)),
	\"amount_msat\" : \"$((payment_amount+18))msat\",
	\"delay\" : 117
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+17)),
	\"amount_msat\" : \"$((payment_amount+17))msat\",
	\"delay\" : 111
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+16)),
	\"amount_msat\" : \"$((payment_amount+16))msat\",
	\"delay\" : 105
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+15)),
	\"amount_msat\" : \"$((payment_amount+15))msat\",
	\"delay\" : 99
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+14)),
	\"amount_msat\" : \"$((payment_amount+14))msat\",
	\"delay\" : 93
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+13)),
	\"amount_msat\" : \"$((payment_amount+13))msat\",
	\"delay\" : 87
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+12)),
	\"amount_msat\" : \"$((payment_amount+12))msat\",
	\"delay\" : 81
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+11)),
	\"amount_msat\" : \"$((payment_amount+11))msat\",
	\"delay\" : 75
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+10)),
	\"amount_msat\" : \"$((payment_amount+10))msat\",
	\"delay\" : 69
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+9)),
	\"amount_msat\" : \"$((payment_amount+9))msat\",
	\"delay\" : 63
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+8)),
	\"amount_msat\" : \"$((payment_amount+8))msat\",
	\"delay\" : 57
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+7)),
	\"amount_msat\" : \"$((payment_amount+7))msat\",
	\"delay\" : 51
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+6)),
	\"amount_msat\" : \"$((payment_amount+6))msat\",
	\"delay\" : 45
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+5)),
	\"amount_msat\" : \"$((payment_amount+5))msat\",
	\"delay\" : 39
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+4)),
	\"amount_msat\" : \"$((payment_amount+4))msat\",
	\"delay\" : 33
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+3)),
	\"amount_msat\" : \"$((payment_amount+3))msat\",
	\"delay\" : 27
 },
{
	\"id\" : \"$alice_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+2)),
	\"amount_msat\" : \"$((payment_amount+2))msat\",
	\"delay\" : 21
 },
{
	\"id\" : \"$bob_id\",
	\"channel\" : \"105x1x0\",
	\"direction\" : 0,
	\"msatoshi\" : $((payment_amount+1)),
	\"amount_msat\" : \"$((payment_amount+1))msat\",
	\"delay\" : 15
 },
]"

echo "route=$route" |& tee -a $log_file

sleep 2s

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc sendpay "$route" $payment_hash  &

sleep 5s

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc waitsendpay $payment_hash


print_channel_balances Bob Alice



