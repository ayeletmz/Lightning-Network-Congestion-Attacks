#!/bin/bash

# actors: Alice, Bob.
# channels: Alice->Bob
# Alice pays Bob several times. Bob pays Alice. They close the channel and withdraw.

HOME='/home/ayelet'
log_file="$HOME/.lightning/logs/exp0_basic_$(date +'%d-%m-%Y-%H:%M:%S').log"

Alice_port=27592
Bob_port=27593
amount_to_insert_lwallet=6
amount_to_insert_channel=16777215
payment_amount=3000000000

. $HOME/.lightning/scripts/functions.sh -G $log_file

$HOME/.lightning/scripts/start_nodes.sh -G $log_file

create_channel Alice Bob $Bob_port $amount_to_insert_lwallet $amount_to_insert_channel

withdraw_remaining_amount Alice

pay Alice Bob $payment_amount
print_channel_balances Alice Bob
pay Alice Bob $payment_amount
print_channel_balances Alice Bob
pay Alice Bob $payment_amount
print_channel_balances Alice Bob

pay Bob Alice $payment_amount
print_channel_balances Alice Bob

close_channel Alice Bob

withdraw_remaining_amount Alice

withdraw_remaining_amount Bob
