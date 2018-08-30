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
echo
echo "Executing docker run command"
echo
if [ "$RUN" == "True" ]; then
    docker run -it -p 0.0.0.0:5151:5151 $DOCKER_NAME $*
else
    echo
    echo "Starting docker with /usr/bin/env bash"
    echo "ENTRYPOINT and CMD defined as:"
    egrep "ENTRYPOINT|CMD" Dockerfile
    echo
    docker run -it -p 0.0.0.0:5151:5151 -e "DEBUG=TRUE" $VOLCMD -it $DOCKER_NAME /usr/bin/env bash
fi
