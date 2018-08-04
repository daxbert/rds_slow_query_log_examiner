#!/usr/bin/env bash
echo "Sourcing config..."
. ./config

echo "Testing environment variables..."
if ( ! ( ( Test-Path "Env:AWS_ACCESS_KEY_ID" ) -and ( Test-Path "Env:AWS_SECRET_ACCESS_KEY" ) ) ){
    echo "AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY undefined"
    echo "Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
    echo ""
    echo "Set-Item -Path Env:AWS_ACCESS_KEY_ID -Value 'AKIA...'"
    echo "Set-Item -Path Env:AWS_SECRET_ACCESS_KEY -Value '#########'"
    echo ""
    exit 1
}
echo ""
echo "Executing docker run command"
echo ""
    docker run -it -p 0.0.0.0:5150:5150 -e "AWS_ACCESS_KEY_ID=$Env:AWS_ACCESS_KEY_ID" -e "AWS_SECRET_ACCESS_KEY=$Env:AWS_SECRET_ACCESS_KEY" $Env:DOCKER_NAME
