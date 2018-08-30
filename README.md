# RDS Slow Query Log

High Level Overview
================================

Amazon RDS can be configured to put its slow query logs into CloudWatch logs.  This is a tool 
to report on these logs. This is not very performant due to AWS CW log APIs being a bit slow. 

Right now this only supports MySQL logs.  

TODO:  postgres

## EASY MODE

1. Add "docker" to your hosts file
   ```
   docker 192.168.99.100
   ```
2. Run the pre-built container from Docker Hub:
   ```
   # docker run -it -p 0.0.0.0:5151:5151 daxchegg/rds_slow_query_log_examiner
   ```

3. Navigate to https://docker:5151/

4. Optionally add the "cert" to your trusted certs


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

* Navigate to ```https://docker:5151/``` 

    0. You may need to login... use AWS credentials which have *TODO* privileges
    1. Click on the AWS Region to examine  ( e.g. us-east-1 )
    2. Select from the list of active CloudWatch RDS logs
    3. After some time ( ~ 1 minute ) the aggregate slow query data will be displayed
    4. Optionally choose a different start/end time
        1. There's currently a limit of 20,000 queries  / log entries to aggregate regardless of the window specified
        2. If the limit is reached, the time window will refect the time window processed rather than requested

## Screenshots

SCREENSHOTS TO FOLLOW



## DEVELOPMENT

See *CONTRIBUTE.md* for instructions on how to contribute to this project

The instructions below assume you have bash and docker installed on your computer 

## How to build the container

```bash
./build.sh
```

## How to run the container: DEV MODE

In dev mode, you can edit the files in the container
and they will persist when the container is stopped.
Mounts are used to achieve this persistence.

## How to run container normally

Unlike dev mode, run mode has no mounts, and therefore
nothing will survive container stoppage.

```
#!bash
./build.sh
./run.sh
```

Optionally, you can run from Docker Hub as shown above.

# FILES and what they do

## HELPER SCRIPTS

* The .sh files should work on Linux/Mac 
* The .ps1 files should work for Windows Powershell

#### ```build.sh``` / ```build.ps1```

Calls clean and then builds the container image

#### ```clean.sh``` / ```clean.ps1```

Purges files to keep them from appearing in the container image

#### ```deploy.sh``` / ```deploy.ps1```

Deploys the current docker image to Docker Hub

#### ```dev.sh```

Runs the container in DEV MODE. ( see DEV MODE below )

#### ```run.sh``` / ```run.ps1```

Runs the container normally. 

#### ```docker_setup.ps1```

If you're on Windows, run this to get the docker-machine running
and get your environment variables set properly for the 
other docker commands.

## Config scripts

#### ```config``` | ```config.ps1```

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

### ```rootfs/apps/rds_slow_query_logs/www/ssl/*```

The various files needed to run this app over SSL ( self-signed cert )

### ```rootfs/apps/rds_slow_query_logs/www/templates/*```

The various flask templates and includes used to render the web app

