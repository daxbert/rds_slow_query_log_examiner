# RDS Slow Query Log

High Level Overview
================================

RDS puts it's slow query logs into CloudWatch logs.  This is a tool to report on these logs.

Goal is to get this into a web service.

## HOW IT WORKS

1)  Provide a list of RDS slow query logs
2)  Given one is selected show the aggregate data for the past 4 hours
3)  Allow tuning of time window

## FILES and what they do

### rootfs/apps/rds_slow_query_logs/...

## DEVELOPMENT


### build the container locally

```
#!bash
./build.sh
```

### run the container locally in dev mode

In dev mode, you can edit the file in the container
and they will persist when the container is stopped.
Mounts are used to achieve this persistence.

```
#!bash
export AWS_DEFAULT_PROFILE={profile_with_your_aws_keys}
./dev.sh
```

### run the container locally in "run" mode

Unlike dev mode, run mode has no mounts, and therefore
nothing will survive container stoppage.

```
#!bash
./build.sh
export AWS_DEFAULT_PROFILE={profile_with_your_aws_keys}
./run.sh
```

## PRODUCITON

This is not likely to make it to a PROD service.  For now
just run locally.

