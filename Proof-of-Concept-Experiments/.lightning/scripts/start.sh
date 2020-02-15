#!/bin/bash

HOME='/home/ayelet'

log_file=$2

. $HOME/.lightning/scripts/logger.sh

$HOME/.bitcoin/start.sh &>> $log_file


$HOME/lightning/lightningd/lightningd --conf=$HOME/.lightning/Alice/config &
$HOME/lightning/lightningd/lightningd --conf=$HOME/.lightning/Bob/config &
$HOME/lightning/lightningd/lightningd --conf=$HOME/.lightning/Crol/config &
$HOME/lightning/lightningd/lightningd --conf=$HOME/.lightning/Dave/config &
$HOME/lightning/lightningd/lightningd --conf=$HOME/.lightning/Eve/config &

sleep 1s

while ! grep "Server started" $HOME/.lightning/Eve/lightningd_Eve.log > /dev/null
do
    sleep 1s
done

einfo "lightning is up" |& tee -a $log_file




