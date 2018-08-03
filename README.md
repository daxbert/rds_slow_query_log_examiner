# RDS Slow Query Log

High Level Overview
================================

Amazon RDS can be configured to put its slow query logs into CloudWatch logs.  This is a tool 
to report on these logs. This is not very performant due to AWS CW log APIs being a bit slow. 

Right now this only supports MySQL logs.  

TODO:  postgres

## EASY MODE

Just run the pre-built container from Docker Hub:

```
docker run -it -p 0.0.0.0:5150:5150 \
-e "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" \
-e "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" \
daxchegg/rds_slow_query_log_examiner
```

## HOW IT WORKS

* You'll first need a running MySQL RDS instance in the Amazon cloud
  * This will need to have ```slow_query_log = 1``` and ```long_query_time``` set as needed

* Build the docker container locally, or run from Docker hub as shown above.

```bash
./build.sh
```

* If building locally, start docker container 
```./run.sh```<p> 
```
2018-08-03 13:31:13,731 - rds_slow_query_log_examiner - INFO - Starting server...
 * Serving Flask app "app" (lazy loading)
 * Environment: production
   WARNING: Do not use the development server in a production environment.
   Use a production WSGI server instead.
 * Debug mode: off
 * Running on http://0.0.0.0:5150/ (Press CTRL+C to quit)
``` 

* Navigate to ```http://localhost:5150/``` 

1. Click on the AWS Region to examine  ( e.g. us-east-1 )
2. Select from the list of active CloudWatch RDS logs
3. After some time ( ~ 1 minute ) the aggregate slow query data will be displayed
4. Optionally choose a different start/end time
    1. There's currently a limit of 20,000 queries  / log entries to aggregate regardless of the window specified
    2. If the limit is reached, the time window will refect the time window processed rather than requested

## Screenshots

SCREENSHOTS TO FOLLOW



## DEVELOPMENT

The instructions below assume you have bash and docker installed on your computer 

## How to build the container

```bash
./build.sh
```

## How to run the container: DEV MODE

In dev mode, you can edit the files in the container
and they will persist when the container is stopped.
Mounts are used to achieve this persistence.

```bash
export AWS_DEFAULT_PROFILE={profile_with_your_aws_keys}
./dev.sh
```

## How to run container normally

Unlike dev mode, run mode has no mounts, and therefore
nothing will survive container stoppage.

```
#!bash
./build.sh
export AWS_DEFAULT_PROFILE={profile_with_your_aws_keys}
./run.sh
```

Optionally, you can run from Docker Hub as shown above.

# FILES and what they do

## HELPER SCRIPTS

#### ```build.sh```

Calls clean.sh and then builds the container image

#### ```clean.sh```

Purges files to keep them from appearing in the container image

#### ```deploy.sh```

Deploys the current docker image to Docker Hub

#### ```dev.sh```

Runs the container in DEV MODE. ( see DEV MODE below )

#### ```run.sh```

Runs the container normally. 

## Config scripts

#### ```config```

Meant to be sourced by the various helper scripts.  This checks that 
``` docker info ``` works and sets the docker repo name

#### ```Dockerfile```

Used to specify the docker container build. duh?

#### ```LICENSE```

MIT License 

#### ```README.md```

This file. duh?

## The working bits...
### ```rootfs/apps/rds_slow_query_logs/www/app.py```

This is the main application entry point.  Right now it's a monolith.  This should
be modularized and made more pythonic.  For now, it's ugly and it works.

### ```rootfs/apps/rds_slow_query_logs/www/templates/*```

The various flask templates and includes used to render the web app

### ```rootfs/apps/rds_slow_query_logs/www/grabLogsFromCWToFile.py```

For advanced users, lets you dump CW logs to a normal MySQL slow query log.  
This will eventually be used to run ```pt-query-digest``` for mo' better log processing. 
