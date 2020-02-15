#!/bin/bash

HOME='/home/ayelet'

. $HOME/.lightning/scripts/logger.sh

log_file=$2

########################### utilities/general ###########################

clean_files() {
	####### Delete old files (for a clean start) #######

	cd $HOME/.bitcoin/Alice
	echo -e "lightning\n" | sudo -S rm -rf $(ls -A | grep -v bitcoin.conf) &>/dev/null
	cd $HOME/.bitcoin/Bob
	echo -e "lightning\n" | sudo -S rm -rf $(ls -A | grep -v bitcoin.conf) &>/dev/null
	cd $HOME/.bitcoin/Crol
	echo -e "lightning\n" | sudo -S rm -rf $(ls -A | grep -v bitcoin.conf) &>/dev/null
	cd $HOME/.bitcoin/Dave
	echo -e "lightning\n" | sudo -S rm -rf $(ls -A | grep -v bitcoin.conf) &>/dev/null
	cd $HOME/.bitcoin/Eve
	echo -e "lightning\n" | sudo -S rm -rf $(ls -A | grep -v bitcoin.conf) &>/dev/null
	cd $HOME/.bitcoin/Network
	echo -e "lightning\n" | sudo -S rm -rf $(ls -A | grep -v bitcoin.conf) &>/dev/null

	cd $HOME/.lightning/Alice
	echo -e "osboxes.org\n" | sudo -S rm -rf $(ls -A | grep -v config) &>/dev/null
	cd $HOME/.lightning/Bob
	echo -e "osboxes.org\n" | sudo -S rm -rf $(ls -A | grep -v config) &>/dev/null
	cd $HOME/.lightning/Crol
	echo -e "osboxes.org\n" | sudo -S rm -rf $(ls -A | grep -v config) &>/dev/null
	cd $HOME/.lightning/Dave
	echo -e "osboxes.org\n" | sudo -S rm -rf $(ls -A | grep -v config) &>/dev/null
	cd $HOME/.lightning/Eve
	echo -e "osboxes.org\n" | sudo -S rm -rf $(ls -A | grep -v config) &>/dev/null

	cd $HOME
}

# input is n: the number of txs we are waiting to enter the mempool
wait_for_n_txs_to_enter_mempool() {
	pool_tx=$(bitcoin-cli -datadir=$HOME/.bitcoin/Network getrawmempool)
	num_tx_in_pool=$(jq '. | length' <<< "$pool_tx")

	while [ "$num_tx_in_pool" -ne "$1" ]
	do
	 sleep 1s
	 pool_tx=$(bitcoin-cli -datadir=$HOME/.bitcoin/Network getrawmempool)
	 num_tx_in_pool=$(jq '. | length' <<< "$pool_tx")
	done
}


print_balances() {
	einfo "\nBalances: Alice=$(bitcoin-cli -datadir=$HOME/.bitcoin/Alice getbalance), Bob=$(bitcoin-cli -datadir=$HOME/.bitcoin/Bob getbalance), Crol=$(bitcoin-cli -datadir=$HOME/.bitcoin/Crol getbalance), Dave=$(bitcoin-cli -datadir=$HOME/.bitcoin/Dave getbalance), Eve=$(bitcoin-cli -datadir=$HOME/.bitcoin/Eve getbalance), Network=$(bitcoin-cli -datadir=$HOME/.bitcoin/Network getbalance)" |& tee -a $log_file
}

# input is n: the number of blocks to mine
mine_n_blocks_to_confirm_txs() {
	einfo "\n####### Network mines $1 blocks to confirm the previous tx #######" &>> $log_file

	bitcoin-cli -datadir=$HOME/.bitcoin/Network generatetoaddress $1 $(bitcoin-cli -datadir=$HOME/.bitcoin/Network  getnewaddress) &>> $log_file
}

# input is node1, node2
print_channel_balances() {
	sleep 1s
	channel_id=''
	get_channel_id $1 $2 channel_id
	if [ -z "$channel_id" ]; then
		einfo "There is no channel between $1 and $2" |& tee -a $log_file
		return
	fi
	channel_list=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listchannels)
	channel=$(jq "[.channels[] | select(.short_channel_id == \"$channel_id\")][0]" <<< "$channel_list")
	channel_total_sat=$(jq ".satoshis" <<< "$channel")
	source_node=''
	get_node_id $1 source_node
	destination_node=''
	get_node_id $2 destination_node
	funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	funds_source_sat=$(jq ".channels[] | select(.peer_id == \"$destination_node\") | .channel_sat" <<< "$funds")
	funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$2/lightning-rpc listfunds)
	funds_destination_sat=$(jq ".channels[] | select(.peer_id == \"$source_node\") | .channel_sat" <<< "$funds")
	einfo "\nChannel $channel_id Balances (sat): Channel_total=$channel_total_sat, $1=$funds_source_sat, $2=$funds_destination_sat" |& tee -a $log_file
}

# input is node, return node_id
get_node_id(){
	neighbour_id=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc getinfo)
	neighbour_id=$(jq '.id' <<< "$neighbour_id" | tr -d '"')
	eval "$2=$neighbour_id"
}

# input is node
wait_for_output_to_be_confirmed(){
	funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	output_status=$(jq '.outputs[0].status' <<< "$funds" | tr -d '"')
	while [ "$output_status" != "confirmed" ]
	do
		sleep 1s
		funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
		output_status=$(jq '.outputs[0].status' <<< "$funds" | tr -d '"')
	done
}

# inputs are node1, node2, return channel_id
get_channel_id(){
	neighbour_id=''
	get_node_id $2 neighbour_id

	channel_id=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	channel_id=$(jq ".channels[] | select(.peer_id == \"$neighbour_id\") | .short_channel_id" <<< "$channel_id"  | tr -d '"')
	eval "$3=$channel_id"
}

# inputs source_id, destination_id, source
# Checks that there exists a channel for the source_id
wait_channel_become_public(){
	source_channel_list=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$3/lightning-rpc listchannels source=$1)
	channel=$(jq ".channels[] | select(.destination == \"$2\")" <<< "$source_channel_list")
	public=$(jq ".public" <<< "$channel")
	while [ ! $public ]
	do	
	    sleep 1s
	    source_channel_list=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$3/lightning-rpc listchannels source=$1)
	    channel=$(jq ".channels[] | select(.destination == \"$2\")" <<< "$source_channel_list")
	    public=$(jq ".public" <<< "$channel")
	done
}

# input is node
#TODO change when there will be more then one payment
mine_until_htlc_timeouts() {
	cltv=$(sed -n '/cltv=/{s/.*cltv=//;p;q}' $HOME/.lightning/$1/lightningd_$1.log | cut -f 1 -d " ")

	num_of_blocks=$(bitcoin-cli -datadir=$HOME/.bitcoin/Network getblockcount)
	edebug "$1 has HTLC with cltv=$cltv. There are $num_of_blocks blocks on the blockchain."
	if [ $((cltv-num_of_blocks)) -ge 0 ]; then
		mine_n_blocks_to_confirm_txs $((cltv-num_of_blocks))
		edebug "mined $((cltv-num_of_blocks)) blocks"
	fi	
}

########################### create channel ###########################


# inputs are node1, node2, node2_port: 
open_peer() {
	####### $1 opens a peer to $2 #######
	neighbour_id=''
	get_node_id $2 neighbour_id

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc connect $neighbour_id@10.0.2.15:$3 &>/dev/null

	einfo "\n$1 created a peer to $2"  |& tee -a $log_file
}


# inputs are node, amount:  node create address and transfers amount into it
generate_btc_address_for_lightning_wallet() {
	####### $1 generates a new address for the lightning wallet #######

	einfo "\n####### $1 generates a new address for the lightning wallet #######" &>> $log_file

	new_addr=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc newaddr)

	new_addr=$(jq '.bech32' <<< "$new_addr")

	new_addr=`echo $new_addr | cut -c 2-45`
	einfo "$1 created a new bitcoin address for the lightning wallet:\n$new_addr" |& tee -a $log_file

	####### $1 transfers $2 btc to the new address #######

	tx_id=$(bitcoin-cli -datadir=$HOME/.bitcoin/$1 sendtoaddress $new_addr $2)
	einfo "$1 sent $2 btc to this address." |& tee -a $log_file
	einfo "tx_id:$tx_id" &>> $log_file

	wait_for_n_txs_to_enter_mempool 1
	mine_n_blocks_to_confirm_txs 1
	wait_for_n_txs_to_enter_mempool 0

	funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	num_of_outputs=$(jq '.outputs |length' <<< "$funds")

	while [ "$num_of_outputs" -eq "0" ]
	do
	    sleep 1s
	    funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	    num_of_outputs=$(jq '.outputs |length' <<< "$funds")
	done

	einfo "tx $tx_id confirmed"  &>> $log_file

	print_balances
}


# inputs are node1, node2, amount:  node1 opens a channel with amount with node2 
open_channel(){
	####### $1 opens a channel with $2 #######

	einfo "\n####### $1 opens a channel with $2 #######" |& tee -a $log_file
	source_id=''
	get_node_id $1 source_id

	destination_id=''
	get_node_id $2 destination_id

	channel=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc fundchannel $destination_id $3) 
	einfo "$channel" &>> $log_file

	channel_tx=$(jq '.txid' <<< "$channel")
	channel_id=$(jq '.channel_id' <<< "$channel")

	wait_for_n_txs_to_enter_mempool 1
	mine_n_blocks_to_confirm_txs 6 # 1 needed for channel, 6 needed for making it public (for routes)
	wait_for_n_txs_to_enter_mempool 0

	wait_channel_become_public  $source_id $destination_id $1 &>/dev/null
	
	channel_data=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listpeers $destination_id)
	channel_state=$(jq '.peers[0].channels[0].state' <<< "$channel_data")

	while [ "$channel_state" != "\"CHANNELD_NORMAL\"" ]
	do
	    channel_data=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listpeers $destination_id)
	    channel_state=$(jq '.peers[0].channels[0].state' <<< "$channel_data")
	done
	
	short_channel_id==$(jq '.peers[0].channels[0].short_channel_id' <<< "$channel_data")

	wait_for_output_to_be_confirmed $1

	einfo  "tx $pool_tx confirmed"  &>> $log_file

	einfo "channel (short_channel_id=$short_channel_id, channel_id=$channel_id) established and active" |& tee -a $log_file
}

# inputs are node1, node2, node2_port, amount_in_wallet, amount_in_channel:  node1 opens a channel with amount_in_channel with node2 
create_channel(){
	open_peer $1 $2 $3

	generate_btc_address_for_lightning_wallet $1 $4

	open_channel $1 $2 $5	
}

########################### payments ###########################


# input is the node witch withdraws
withdraw_remaining_amount() {
	####### $1 withdraws his/hers remaining money in the lightning channel #######

	einfo "\n####### $1 withdraws his/hers remaining money in the lightning channel #######" |& tee -a $log_file

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc withdraw $(bitcoin-cli -datadir=$HOME/.bitcoin/$1 getnewaddress) 'all' &>> $log_file

	wait_for_n_txs_to_enter_mempool 1
	mine_n_blocks_to_confirm_txs 1
	wait_for_n_txs_to_enter_mempool 0

	funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	num_of_outputs=$(jq '.outputs |length' <<< "$funds")

	while [ "$num_of_outputs" -ne "0" ]
	do
	    sleep 1s
	    funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	    num_of_outputs=$(jq '.outputs |length' <<< "$funds")
	done

	print_balances
}

# inputs are node1, node2, amount:  node1 pays amount to node2
pay() {

	####### $1 transfers money to $2 through the lightning channel #######

	einfo "\n####### $1 transfers money to $2 through the lightning channel #######" |& tee -a $log_file

	bolt11=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$2/lightning-rpc invoice $3 "$1_to_$2-$(date +'%T:%N')" "$(date +'%T:%N') tx of $3 msat from $1 to $2")
	
	einfo "$bolt11" &>> $log_file
	bolt11=$(jq '.bolt11' <<< "$bolt11")

	$HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc pay $bolt11 &>> $log_file

}


########################### close ###########################

# inputs are node1, channel_id
mine_until_channel_is_forgotten(){

	####### Need to wait 100 blocks to channel be forgotten #######
	einfo "####### Need to wait 100 blocks to channel be forgotten #######"  &>> $log_file

	mine_n_blocks_to_confirm_txs 100

	funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	channels_exists=$(jq "[.channels[] |select(.short_channel_id == \"$2\")] | length" <<< "$funds")

	while [ "$channels_exists" -ne "0" ]
	do
	    sleep 1s
	   funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	channels_exists=$(jq "[.channels[] |select(.short_channel_id == \"$2\")] | length" <<< "$funds")
	done

	einfo "channel $channel_id has been closed" |& tee -a $log_file

	num_of_outputs=$(jq '.outputs |length' <<< "$funds")

	while [ "$num_of_outputs" -eq "0" ]
	do
	    sleep 1s
	   funds=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listfunds)
	    num_of_outputs=$(jq '.outputs |length' <<< "$funds")
	done

	einfo "####### $1 can withdraw #######"  &>> $log_file
}

# inputs are node1, node2:  close the channel between them
close_channel(){

	####### $1 closes the channel with $2 #######
	einfo "\n####### $1 closes the channel with $2 #######" |& tee -a $log_file

	channel_id=''
	get_channel_id $1 $2 channel_id
	
	tx_id=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc close $channel_id true)

	einfo "$tx_id" &>> $log_file

	tx_id=$(jq '.txid' <<< "$tx_id")

	wait_for_n_txs_to_enter_mempool 1

	channel_state=$($HOME/lightning/cli/lightning-cli --rpc-file=$HOME/.lightning/$1/lightning-rpc listpeers)
	channel_state=$(jq '.peers[0].channels[0].state' <<< "$channel_state")

	einfo "$channel_state" &>> $log_file
	
	mine_until_channel_is_forgotten $1 $channel_id
}
