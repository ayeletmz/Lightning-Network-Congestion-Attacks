#!/bin/bash

# actors: Alice, Bob, Crol, Dave
# channels: Eve<->Dave<->Alice<->Bob<->Crol
# Alice pays Crol (a route through Bob) s.t. maximum (483) times is achieved.
# Alice pays Eve (a route through Dave) s.t. maximum (483) times is achieved.
# Use case: Crol and Eve do not return their secrets. We overload the paths Alice-Bob-Crol and Alice-Dave-Eve and block them to new payments.
# Here my purpose is to show that max htlc is per channel and not per node, a node can send more than 483 htlcs when it is to different channels.
# Change in c-lightning code: Crol and Eve do not return secrets (invoice.c), before timeout Crol sends update_fail_htlc (peer_htlcs.c).
# Must add Alice to invoice.c line 269:
# if (strcmp((const char*)ld->alias, "Crol") == 0 || strcmp((const char*)ld->alias, "Eve") == 0) 
	
HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp4_max_htlc_is_per_channel_not_node_c_$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
Crol_port=27594
Dave_port=27595
Eve_port=27596
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=100

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

create_channel Bob Crol $Crol_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Bob

create_channel Alice Dave $Dave_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

create_channel Dave Eve $Eve_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Dave

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Alice Dave
print_channel_balances Dave Eve

einfo "\n####### Alice transfers money to Crol through the lightning channel #######" |& tee -a $log_file

for iteration in {1..483}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Alice_to_Crol_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Crol $iteration")
	
	einfo "$bolt11"  &>> $log_file
	
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc pay $bolt11 &

done

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Alice Dave
print_channel_balances Dave Eve


einfo "\n####### Alice transfers money to Eve through the lightning channel #######" |& tee -a $log_file

for iteration in {1..483}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Eve/lightning-rpc invoice $payment_amount "Alice_to_Eve_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Eve $iteration")
	
	einfo "$bolt11"  &>> $log_file
	
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc pay $bolt11 &

done

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Alice Dave
print_channel_balances Dave Eve

# Chcek there are no failed payments (i.e. result equal to 0)
$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc listsendpays | grep -c "fail"
# Chcek there are exactly 483 pending payments
 $HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc listsendpays | grep -c "pending"

einfo "\n####### Alice attempts to send money to Crol through the lightning channel - should fail #######" |& tee -a $log_file

for iteration in {484..484}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Alice_to_Crol_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Crol $iteration")
	
	einfo "$bolt11"  &>> $log_file
	
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc pay $bolt11 &

done

einfo "\n####### Alice attempts to send money to Eve through the lightning channel - should fail #######" |& tee -a $log_file

for iteration in {484..484}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Eve/lightning-rpc invoice $payment_amount "Alice_to_Eve_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Eve $iteration")
	
	einfo "$bolt11"  &>> $log_file
	
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc pay $bolt11 &

done


