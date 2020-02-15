#!/bin/bash

# actors: Alice, Bob, Crol
# channels: Alice->Bob->Crol
# Alice pays Crol (a route through Bob) maximum (483) times.
# Use case: Crol does not return her secret. She waits until her htlc (hin) is timed off and right
# before timeout she sends Bob update_fail_htlc what causes failing the payment but keeping all channels along route alive.
# We only overload the path Alice-Bob-Crol and block it to new payments until the cltv expiry passes.
# Change in c-lightning code: Crol does not return secret (invoice.c), before timeout Crol sends update_fail_htlc (peer_htlcs.c).

HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp4_483_payments_$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
Crol_port=27594
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=100

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

create_channel Bob Crol $Crol_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

withdraw_remaining_amount Bob

########## to balance the channel Alice-Bob (so Bob can send Alice too...)
pay Alice Bob 1000000000
print_channel_balances Alice Bob
pay Alice Bob 1000000000
print_channel_balances Alice Bob
pay Alice Bob 1000000000
print_channel_balances Alice Bob	

pay Bob Alice 1000000000
print_channel_balances Alice Bob

##########

einfo "\n####### Alice transfers money to Crol through the lightning channel #######" |& tee -a $log_file

for iteration in {1..483}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Alice_to_Crol_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Crol $iteration")
	
	einfo "$bolt11"  &>> $log_file
	
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc pay $bolt11 &

done



#$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc listinvoices
#$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc listsendpays
#bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount


