#!/usr/bin/env bash

if ( Test-Path "config.ps1" ) {
    . ./config.ps1
} else {
    echo "Unable to find config file 'config.ps1'"
    exit 1
}
echo $Env:DOCKER_NAME
echo $Env:REPO_NAME

echo "Starting Deploy..."
Test-Path $Env:DOCKER_NAME
echo $?

if ( ( Test-Path 'Env:DOCKER_NAME' ) -and ( Test-Path 'Env:REPO_NAME' ) ) {
    docker build -t $Env:DOCKER_NAME . 
    docker tag ${Env:DOCKER_NAME}:latest ${Env:REPO_NAME}/${Env:DOCKER_NAME}:latest
    docker push ${Env:REPO_NAME}/${Env:DOCKER_NAME}:latest
} else {
    echo "DOCKER_NAME and/or REPO_NAME not set"
    exit 1
}
    
exit 0

