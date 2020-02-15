#!/bin/bash

# actors: Alice, Bob, Crol
# channels: Crol->Alice->Bob->Crol
# Phase 1: Crol pays Bob through a route she specifies.
# Phase 2: Crol pays herself (a circle route through Alice and Bob)
# Phase 3: Crol pays Alice using a loop.
# Use case: Works with the original c-lightning code (not changed). 
# This script shows that a circle can be implemented (running phase 2 is enough, see send pay status ('complete') plus fees in final balance, can also look at listforwards).

HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp5_basic_routes_and_loops$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
Crol_port=27594
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=100000000

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

create_channel Bob Crol $Crol_port $amount_to_insert_lwallet $amount_to_insert_channel

create_channel Crol Alice $Alice_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

withdraw_remaining_amount Bob

withdraw_remaining_amount Crol


alice_id=''
get_node_id Alice alice_id
bob_id=''
get_node_id Bob bob_id
crol_id=''
get_node_id Crol crol_id
sleep 2s

edebug "number of blocks: $(bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount)" |& tee -a $log_file

#### Phase 1: Crol pays Bob #####

einfo "\n####### Phase 1: Crol pays Bob #######" |& tee -a $log_file

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Crol Alice

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc invoice $payment_amount "to Bob-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat to Bob")

einfo "$inv" |& tee -a $log_file

payment_hash=$(jq '.payment_hash' <<< "$inv")

alice_id=''
get_node_id Alice alice_id
bob_id=''
get_node_id Bob bob_id
crol_id=''
get_node_id Crol crol_id

route="[
   {
    \"id\" : \"$alice_id\",
    \"channel\" : \"118x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+10000)),
    \"amount_msat\" : \"$((payment_amount+10000))msat\",
    \"delay\" : 15
 },
 {
    \"id\" : \"$bob_id\",
    \"channel\" : \"104x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $payment_amount,
    \"amount_msat\" : \"${payment_amount}msat\",
    \"delay\" : 9
 }
]"

echo "route=$route" |& tee -a $log_file

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc sendpay "$route" $payment_hash 

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc waitsendpay $payment_hash

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Crol Alice

#### Phase 2: Crol pays herself #####

einfo "\n####### Phase 2: Crol transfers money to herself through the lightning channel in a circular route #######" |& tee -a $log_file

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "a-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat a")

einfo "$inv" |& tee -a $log_file

payment_hash=$(jq '.payment_hash' <<< "$inv")

route="[
   {
    \"id\" : \"$alice_id\",
    \"channel\" : \"118x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+20000)),
    \"amount_msat\" : \"$((payment_amount+20000))msat\",
    \"delay\" : 21
 },
 {
    \"id\" : \"$bob_id\",
    \"channel\" : \"104x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+10000)),
    \"amount_msat\" : \"$((payment_amount+10000))msat\",
    \"delay\" : 15
 },
{
    \"id\" : \"$crol_id\",
    \"channel\" : \"111x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $payment_amount,
    \"amount_msat\" : \"${payment_amount}msat\",
    \"delay\" : 9
 }
]"

echo "route=$route" |& tee -a $log_file

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc sendpay "$route" $payment_hash 

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc waitsendpay $payment_hash

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Crol Alice

#### Phase 3: Crol pays Alice using a loop #####

einfo "\n####### Phase 3: Crol pays Alice using a loop #######" |& tee -a $log_file

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc invoice $payment_amount "a-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat a")

einfo "$inv" |& tee -a $log_file

payment_hash=$(jq '.payment_hash' <<< "$inv")

route="[
   {
    \"id\" : \"$alice_id\",
    \"channel\" : \"118x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+30000)),
    \"amount_msat\" : \"$((payment_amount+30000))msat\",
    \"delay\" : 27
 },
 {
    \"id\" : \"$bob_id\",
    \"channel\" : \"104x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+20000)),
    \"amount_msat\" : \"$((payment_amount+20000))msat\",
    \"delay\" : 21
 },
{
    \"id\" : \"$crol_id\",
    \"channel\" : \"111x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+10000)),
    \"amount_msat\" : \"$((payment_amount+10000))msat\",
    \"delay\" : 15
 },
{
    \"id\" : \"$alice_id\",
    \"channel\" : \"118x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $payment_amount,
    \"amount_msat\" : \"${payment_amount}msat\",
    \"delay\" : 9
 }
]"

echo "route=$route" |& tee -a $log_file

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc sendpay "$route" $payment_hash 

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc waitsendpay $payment_hash

print_channel_balances Alice Bob
print_channel_balances Bob Crol
print_channel_balances Crol Alice
