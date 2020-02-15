#!/bin/bash

# actors: Alice, Bob, Crol
# channels: Alice->Bob->Crol
# Alice pays Crol (a route through Bob)

HOME='/home/ayelet'
log_file="$HOME/.lightning/logs/exp2_simple_route_$(date +'%d-%m-%Y-%H:%M:%S').log"

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

pay Alice Crol $payment_amount

print_channel_balances Alice Bob
print_channel_balances Bob Crol
