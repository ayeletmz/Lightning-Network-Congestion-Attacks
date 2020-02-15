#!/bin/bash

HOME='/home/ayelet'

. $HOME/.lightning/scripts/logger.sh

# Network should run first since the other connect to it.
bitcoind -datadir=$HOME/.bitcoin/Network/ -regtest -conf=$HOME/.bitcoin/Network/bitcoin.conf -daemon -debug

bitcoind -datadir=$HOME/.bitcoin/Alice/ -regtest -conf=$HOME/.bitcoin/Alice/bitcoin.conf -daemon -debug
bitcoind -datadir=$HOME/.bitcoin/Bob/ -regtest -conf=$HOME/.bitcoin/Bob/bitcoin.conf -daemon -debug
bitcoind -datadir=$HOME/.bitcoin/Crol/ -regtest -conf=$HOME/.bitcoin/Crol/bitcoin.conf -daemon -debug
bitcoind -datadir=$HOME/.bitcoin/Dave/ -regtest -conf=$HOME/.bitcoin/Dave/bitcoin.conf -daemon -debug
bitcoind -datadir=$HOME/.bitcoin/Eve/ -regtest -conf=$HOME/.bitcoin/Eve/bitcoin.conf -daemon -debug


while ! grep "net thread start" $HOME/.bitcoin/Eve/regtest/debug.log > /dev/null
do
    sleep 1s
done

einfo "bitcoin is up"
