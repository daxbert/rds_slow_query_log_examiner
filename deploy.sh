#!/usr/bin/env bash

if [ -f "config" ]; then
    source config
else
    echo Unable to find config file 'config'
    exit 1
fi

echo "Starting Deploy..."
if [ -n "$DOCKER_NAME" ] && [ -n "$REPO_NAME" ]; then
    docker build -t $DOCKER_NAME . 
    docker tag $DOCKER_NAME:latest $REPO_NAME/$DOCKER_NAME:latest
    docker push $REPO_NAME/$DOCKER_NAME:latest
else
    echo "DOCKER_NAME and/or REPO_NAME not set"
    exit 1
fi
    
exit 0

