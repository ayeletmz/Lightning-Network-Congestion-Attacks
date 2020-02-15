#!/bin/bash

HOME='/home/ayelet'

bitcoin-cli -datadir=$HOME/.bitcoin/Alice/ stop
bitcoin-cli -datadir=$HOME/.bitcoin/Bob/ stop
bitcoin-cli -datadir=$HOME/.bitcoin/Crol/ stop
bitcoin-cli -datadir=$HOME/.bitcoin/Dave/ stop
bitcoin-cli -datadir=$HOME/.bitcoin/Eve/ stop
bitcoin-cli -datadir=$HOME/.bitcoin/Network/ stop
