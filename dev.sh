#!/usr/bin/env bash

source config

PWD=`pwd`/rootfs
DIRS=`ls rootfs`
echo

VOLCMD=""
RUN=""
SCRIPT=`basename $0`
if [ "$SCRIPT" == "run.sh" ]; then 
    echo "Starting Docker in RUN Mode"
    RUN="True"
else
    echo "Starting Docker in DEV Mode"
    echo "In DEV Mode, the following mounts will occur and permit"
    echo "edits to persist even after the container has been stopped"
    echo
    echo "Paths to Mount:"
    for DIR in $DIRS; do
        echo "$PWD/$DIR ---> /$DIR"
        VOLCMD="$VOLCMD -v $PWD/$DIR:/$DIR "
    done
fi
echo
if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" ]]; then
    echo "AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY undefined"
    if [ -z "$AWS_DEFAULT_PROFILE" ]; then
        echo "Also, AWS_DEFAULT_PROFILE undefined, can't proceed."
        echo "Either:"
        echo
        echo "Export AWS_DEFAULT_PROFILE to point "
        echo "to the desired AWS Credentials for this "
        echo "run."
        echo ""
        echo "EXAMPLE: "
        echo "export AWS_DEFAULT_PROFILE=someprofile"
        echo 
        echo "OR"
        echo
        echo "Export both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
        echo
        echo "export AWS_ACCESS_KEY_ID=AKIA..."
        echo "export AWS_SECRET_ACCESS_KEY=###################"
        echo
        exit 1
    else
        echo "AWS_DEFAULT_PROFILE defined"
    fi
    echo "Will attempt to parse keys from credentials file"
    echo "for the profile specified"
    echo "This could be improved..."
    echo
    AWS_ACCESS_KEY_ID=`grep -A2 $AWS_DEFAULT_PROFILE ~/.aws/credentials  | grep aws_access_key_id | awk '{print $3}'`
    if [[ $AWS_ACCESS_KEY_ID = AKIA* ]]; then
        echo "Parsing likely worked... AKIA pattern found for ACCESS_KEY_ID"
        AWS_SECRET_ACCESS_KEY=`grep -A2 $AWS_DEFAULT_PROFILE ~/.aws/credentials  | grep aws_secret_access_key | awk '{print $3}'`
    else
        echo "Parsing failed.  Please export AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
        exit 1
    fi
fi
echo
echo "Executing docker run command"
echo
if [ "$RUN" == "True" ]; then
    docker run -it -p 0.0.0.0:5150:5150 -e "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" -e "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" $DOCKER_NAME $*
else
    echo
    echo "Starting docker with /usr/bin/env bash"
    echo "ENTRYPOINT and CMD defined as:"
    egrep "ENTRYPOINT|CMD" Dockerfile
    echo
    docker run -it -p 0.0.0.0:5150:5150 -e "DEBUG=TRUE" -e "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" -e "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" $VOLCMD -it $DOCKER_NAME /usr/bin/env bash
fi
