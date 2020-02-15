#!/bin/bash

HOME='/home/ayelet'

log_file=$2

. $HOME/.lightning/scripts/functions.sh -G $log_file
. $HOME/.lightning/scripts/logger.sh

####### stop servers if runnings #######

$HOME/.lightning/scripts/stop.sh &>> $log_file

sleep 1s

####### Delete old files (for a clean start) #######

clean_files

####### Start servers #######

$HOME/.lightning/scripts/start.sh -G $log_file

####### Network mines 102 blocks to gain initial BTC #######

einfo "\n####### Network mines 102 blocks to gain initial BTC #######" |& tee -a $log_file

bitcoin-cli -datadir=$HOME/.bitcoin/Network generatetoaddress 102 $(bitcoin-cli -datadir=$HOME/.bitcoin/Network  getnewaddress) &>> $log_file

####### Network passes 10 ETH to each node #######

einfo "\n####### Network passes 10 ETH to each node #######" |& tee -a $log_file

bitcoin-cli -datadir=$HOME/.bitcoin/Network sendtoaddress $(bitcoin-cli -datadir=$HOME/.bitcoin/Alice getnewaddress) 10 &>> $log_file
 
bitcoin-cli -datadir=$HOME/.bitcoin/Network sendtoaddress $(bitcoin-cli -datadir=$HOME/.bitcoin/Bob getnewaddress) 10 &>> $log_file

bitcoin-cli -datadir=$HOME/.bitcoin/Network sendtoaddress $(bitcoin-cli -datadir=$HOME/.bitcoin/Crol getnewaddress) 10 &>> $log_file

bitcoin-cli -datadir=$HOME/.bitcoin/Network sendtoaddress $(bitcoin-cli -datadir=$HOME/.bitcoin/Dave getnewaddress) 10 &>> $log_file

bitcoin-cli -datadir=$HOME/.bitcoin/Network sendtoaddress $(bitcoin-cli -datadir=$HOME/.bitcoin/Eve getnewaddress) 10 &>> $log_file

wait_for_n_txs_to_enter_mempool 5
mine_n_blocks_to_confirm_txs 1
wait_for_n_txs_to_enter_mempool 0

print_balances

neighbour_id=''
get_node_id Alice neighbour_id
edebug "Alice's id: $neighbour_id" |& tee -a $log_file

neighbour_id=''
get_node_id Bob neighbour_id
edebug "Bob's id: $neighbour_id" |& tee -a $log_file

neighbour_id=''
get_node_id Crol neighbour_id
edebug "Crol's id: $neighbour_id" |& tee -a $log_file

neighbour_id=''
get_node_id Dave neighbour_id
edebug "Dave's id: $neighbour_id" |& tee -a $log_file

neighbour_id=''
get_node_id Eve neighbour_id
edebug "Eve's id: $neighbour_id" |& tee -a $log_file

edebug "number of blocks: $(bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount)" |& tee -a $log_file
