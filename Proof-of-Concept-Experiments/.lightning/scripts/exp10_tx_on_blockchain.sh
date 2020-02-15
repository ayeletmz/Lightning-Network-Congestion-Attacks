#!/bin/bash

# actors: Alice, Bob, Crol, Dave, Eve
# channels: Eve<->Dave<->Alice<->Bob<->Crol
# Eve pays Crol maximum (483) times.
# Use case: Crol does not return secrets. We overload the path and block the channels along it to new payments.
# We close the channel between Crol and Bob and then kill Bob (forcing unilateral) and want to view the tx on the blockchain.
# Change in c-lightning code: Crol does not return secret (invoice.c), before timeout Crol sends update_fail_htlc (peer_htlcs.c).
	
HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp10_tx_on_blockchain_$(date +'%d-%m-%Y-%H:%M:%S').log"

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

create_channel Eve Dave $Dave_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Eve

create_channel Dave Alice $Alice_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Dave

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

create_channel Bob Crol $Crol_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Bob

print_channel_balances Eve Dave 
print_channel_balances Dave Alice 
print_channel_balances Alice Bob
print_channel_balances Bob Crol


einfo "\n####### Eve transfers money to Crol through the lightning channel #######" |& tee -a $log_file

alice_id=''
get_node_id Alice alice_id
bob_id=''
get_node_id Bob bob_id
crol_id=''
get_node_id Crol crol_id
dave_id=''
get_node_id Dave dave_id
eve_id=''
get_node_id Eve eve_id
locktime_max=$((14 * 24 * 6))


route="[
   {
    \"id\" : \"$dave_id\",
    \"channel\" : \"105x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+30)),
    \"amount_msat\" : \"$((payment_amount+30))msat\",
    \"delay\" : $locktime_max
 },
 {
    \"id\" : \"$alice_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+20)),
    \"amount_msat\" : \"$((payment_amount+20))msat\",
    \"delay\" : $(( locktime_max - 6))
 },
 {
    \"id\" : \"$bob_id\",
    \"channel\" : \"121x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+10)),
    \"amount_msat\" : \"$((payment_amount+10))msat\",
    \"delay\" : $(( locktime_max - 12))
 },
{
    \"id\" : \"$crol_id\",
    \"channel\" : \"129x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $payment_amount,
    \"amount_msat\" : \"${payment_amount}msat\",
    \"delay\" : $((locktime_max - 12 - 9))
 }
]"

echo "route=$route" |& tee -a $log_file

for iteration in {1..483}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file


	inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Eve_to_Crol_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Eve to Crol $iteration")

	einfo "$inv" |& tee -a $log_file

	payment_hash=$(jq '.payment_hash' <<< "$inv")


	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Eve/lightning-rpc sendpay "$route" $payment_hash &

done

print_channel_balances Eve Dave 
print_channel_balances Dave Alice 
print_channel_balances Alice Bob
print_channel_balances Bob Crol


einfo "\n####### Eve attempts to send money to Crol through the lightning channel - should fail #######" |& tee -a $log_file

for iteration in {484..484}
do
	edebug "\npayment iteration $iteration" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "Alice_to_Eve_$iteration-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat from Alice to Eve $iteration")
	
	einfo "$bolt11"  &>> $log_file
	
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Eve/lightning-rpc pay $bolt11 &

done

close_channel Crol Bob

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Eve/lightning-rpc listsendpays
bitcoin-cli -datadir=$HOME/.bitcoin/Crol getblockchaininfo

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc listpeers

bitcoin-cli -datadir=$HOME/.bitcoin/Network getrawmempool

ps aux | grep lightning
kill -9 Bob_pid

bitcoin-cli -datadir=$HOME/.bitcoin/Network getrawtransaction txid true



