#!/bin/bash

# actors: Alice, Bob, Crol
# channels: Alice->Bob->Crol
# Alice pays Crol (a route through Bob)
# Use case: Crol does not return her secret. This causes Bob to close the channel with Carol once his hout (htlc out from Bob to Crol)
# is timed out, and he sends update_fail_htlc to Alice so they update their tx removing the htlc, keeping their channel alive.
# Change in c-lightning code: Crol does not return secret (invoice.c).

HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp3_attack_does_not_return_secret_$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
Crol_port=27594
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=1000000000

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

create_channel Bob Crol $Crol_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

withdraw_remaining_amount Bob


einfo "\n####### Alice transfers money to Crol through the lightning channel #######" |& tee -a $log_file

bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Alice_to_Crol-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Crol")

einfo "$bolt11" |& tee -a $log_file

bolt11=$(jq '.bolt11' <<< "$bolt11")

sleep 2s

einfo "start" |& tee -a $log_file

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc pay $bolt11 &
proc=$!
 
einfo "done" |& tee -a $log_file

sleep 5s
mine_until_htlc_timeouts Bob #for Bobs htlc time out
mine_n_blocks_to_confirm_txs 1 #time out occurs one block later

sleep 30s
mine_n_blocks_to_confirm_txs 1 #for notifying Alice of htlc failure

sleep 30s
mine_n_blocks_to_confirm_txs 3 #for channel fail get to Alice

sleep 30s
mine_n_blocks_to_confirm_txs 200 # for peer being forgotten

sleep 40s
mine_n_blocks_to_confirm_txs 500 

sleep 70s

wait "$proc"
einfo "finished"

print_channel_balances Alice Bob
print_channel_balances Bob Crol

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc listforwards


if ! grep -q "Channel_total=16777215, Alice=16777215, Bob=0" $log_file || ! ( grep -q "There is no channel between Bob and Crol" $log_file || grep -q "Channel_total=null, Bob=16777215, Crol=" $log_file ) ; then
	eerror "FAILURE"  |& tee -a $log_file
	exit 1
fi

einfo "SUCCESS" 

