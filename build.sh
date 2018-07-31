#!/usr/bin/env bash 

source ./config

./clean.sh

docker build -t $DOCKER_NAME .



