#!/bin/bash

HOME='/home/ayelet'

$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Eve/lightning-rpc stop
$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Dave/lightning-rpc stop
$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Crol/lightning-rpc stop
$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Bob/lightning-rpc stop
$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/Alice/lightning-rpc stop


$HOME/.bitcoin/stop.sh



