#!/bin/bash

# actors: Alice, Bob, Crol, Dave. Eve
# channels: Alice->Bob->Dave->Eve->Bob->Crol
# Use case: Normal (Everyone return secret), path with same loop several times in the middle.

HOME='/home/ayelet'
. $HOME/.lightning/scripts/logger.sh

log_file="$HOME/.lightning/logs/exp8_middle_loop_twice_$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
Crol_port=27594
Dave_port=27595
Eve_port=27596
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=1000000

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

create_channel Bob Dave $Dave_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Bob

create_channel Dave Eve $Eve_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Dave

create_channel Eve Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Eve

create_channel Bob Crol $Crol_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Bob


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
sleep 2s

edebug "number of blocks: $(bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount)" |& tee -a $log_file

print_channel_balances Alice Bob
print_channel_balances Bob Dave
print_channel_balances Dave Eve
print_channel_balances Eve Bob
print_channel_balances Bob Crol

#### Alice pays Crol with loop #####

einfo "\n####### Alice transfers money to Crol through the lightning channel in a route with loop #######" |& tee -a $log_file

inv=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc invoice $payment_amount "a-$(date +'%T:%N')" "$(date +'%T:%N') tx of $payment_amount msat a")

einfo "$inv" |& tee -a $log_file

payment_hash=$(jq '.payment_hash' <<< "$inv")

route="[
 {
    \"id\" : \"$bob_id\",
    \"channel\" : \"105x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+7000)),
    \"amount_msat\" : \"$((payment_amount+7000))msat\",
    \"delay\" : 51
 },
{
    \"id\" : \"$dave_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+6000)),
    \"amount_msat\" : \"$((payment_amount+6000))msat\",
    \"delay\" : 45
 },
{
    \"id\" : \"$eve_id\",
    \"channel\" : \"121x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+5000)),
    \"amount_msat\" : \"$((payment_amount+5000))msat\",
    \"delay\" : 39
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"129x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+4000)),
    \"amount_msat\" : \"$((payment_amount+4000))msat\",
    \"delay\" : 33
 },
,
{
    \"id\" : \"$dave_id\",
    \"channel\" : \"113x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+3000)),
    \"amount_msat\" : \"$((payment_amount+3000))msat\",
    \"delay\" : 27
 },
{
    \"id\" : \"$eve_id\",
    \"channel\" : \"121x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+2000)),
    \"amount_msat\" : \"$((payment_amount+2000))msat\",
    \"delay\" : 21
 },
{
    \"id\" : \"$bob_id\",
    \"channel\" : \"129x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $((payment_amount+1000)),
    \"amount_msat\" : \"$((payment_amount+1000))msat\",
    \"delay\" : 15
 },
{
    \"id\" : \"$crol_id\",
    \"channel\" : \"137x1x0\",
    \"direction\" : 0,
    \"msatoshi\" : $payment_amount,
    \"amount_msat\" : \"${payment_amount}msat\",
    \"delay\" : 9
 }
]"

echo "route=$route" |& tee -a $log_file

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc sendpay "$route" $payment_hash 

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc waitsendpay $payment_hash

print_channel_balances Alice Bob
print_channel_balances Bob Dave
print_channel_balances Dave Eve
print_channel_balances Eve Bob
print_channel_balances Bob Crol

