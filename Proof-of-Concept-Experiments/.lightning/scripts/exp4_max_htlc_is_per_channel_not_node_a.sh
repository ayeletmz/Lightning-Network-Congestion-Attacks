#!/bin/bash

# actors: Alice, Bob, Crol, Dave, Eve
# channels: Alice<->Bob<->Dave<->Eve<->Crol
# Dave pays Crol (a route through Eve), and pays Alice (through Bob) s.t. maximum (483) times is achieved.
# Use case: Crol and Alice do not return their secrets.
# We show that max_htlc is per channel and not per node.
# Change in c-lightning code: Crol and Alice do not return secrets (invoice.c), before timeout Crol sends update_fail_htlc (peer_htlcs.c).
# Must add Alice to invoice.c line 269:
# if (strcmp((const char*)ld->alias, "Crol") == 0 || strcmp((const char*)ld->alias, "Alice") == 0)
	
HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp4_max_htlc_is_per_channel_not_node_a_$(date +'%d-%m-%Y-%H:%M:%S').log"

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

create_channel Bob Dave $Dave_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Bob

create_channel Dave Eve $Eve_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Dave

create_channel Crol Eve $Eve_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Crol

########## to balance the channel Alice-Bob (so Bob can send Alice too...)
pay Alice Bob 4000000000
pay Bob Dave 4000000000
pay Dave Eve 4000000000
pay Crol Eve 4000000000
print_channel_balances Alice Bob
print_channel_balances Bob Dave
print_channel_balances Dave Eve
print_channel_balances Eve Crol
##########

einfo "\n####### Dave transfers money to Crol through the lightning channel #######" |& tee -a $log_file

for iteration in {1..200}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Dave_to_Crol_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Dave to Crol $iteration")
	
	einfo "$bolt11"  &>> $log_file
	
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Dave/lightning-rpc pay $bolt11 &

done

einfo "\n####### Dave transfers money to Alice through the lightning channel #######" |& tee -a $log_file

for iteration in {201..483}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc invoice $payment_amount "Dave_to_Alice_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Dave to Alice $iteration")
	
	einfo "$bolt11"  &>> $log_file
	
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Dave/lightning-rpc pay $bolt11 &

done

# Chcek there are no failed payments (i.e. result equal to 0)
$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Dave/lightning-rpc listsendpays | grep -c "fail"
# Chcek there are exactly 483 pending payments
 $HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Dave/lightning-rpc listsendpays | grep -c "pending"

# Add here more payments and see this isn't a problem

#$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc listinvoices
#$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc listsendpays



