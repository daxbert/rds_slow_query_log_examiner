from flask import Flask, request, redirect, abort, render_template, g, session
import botocore
import time
import logging
import datetime
import boto3
import os
import urllib
from markupsafe import Markup

# import our local classes
from log_entries import LogEntries
from aws_regions import AWSRegions
from cache_lock import CacheLock

aws_regions = None


app = Flask(__name__)

logger = logging.getLogger('rds_slow_query_log_examiner')
logger.setLevel(logging.INFO)
if "DEBUG" in os.environ:
    logger.setLevel(logging.DEBUG)
logger.propagate = False

stderr_logs = logging.StreamHandler()
stderr_logs.setLevel(logging.INFO)
if "DEBUG" in os.environ:
    stderr_logs.setLevel(logging.DEBUG)
stderr_logs.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(stderr_logs)

logger.info('Init Lock Object')
cache_lock = None
web_protocol = ""


@app.before_request
def before_request():
    if 'AWS_ACCESS_KEY_ID' not in session:
        if "credentials" not in request.url:
            if 'AWS_ACCESS_KEY_ID' in os.environ:
                logger.info("Credentials Needed - Environment set, using it.")
                session['AWS_ACCESS_KEY_ID'] = os.environ['AWS_ACCESS_KEY_ID']
                session['AWS_SECRET_ACCESS_KEY'] = os.environ['AWS_SECRET_ACCESS_KEY']
            else:
                logger.info("Credentials Needed - No environment, redirect to login")
                return redirect("/credentials?redirect=" + request.url)


@app.route('/credentials', methods=['GET', 'POST'])
def credentials():
    if "user_id" in request.form:
        session["AWS_ACCESS_KEY_ID"] = request.form["user_id"]
        if "password" in request.form:
            session["AWS_SECRET_ACCESS_KEY"] = request.form["password"]
            if "redirect" in request.args:
                return redirect(request.args["redirect"])
            if "redirect" in request.form:
                return redirect(request.form["redirect"])
    return render_template(
        'credentials.html'
    ), 401


@app.route('/regions', methods=['GET'])
def regions():
    """
    Show Region List
    """

    if 'ec2_client' not in g:
        g.ec2_client = boto3.client(
            'ec2',
            aws_access_key_id=session['AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=session['AWS_SECRET_ACCESS_KEY'],
            region_name='us-west-1'
        )

    global aws_regions
    if aws_regions is None:
        logger.info("aws_regions does not yet exist")
        aws_regions = AWSRegions(g.ec2_client, logger)
    else:
        logger.info("aws_regions exists")

    try:
        return render_template('regions.html', regions=aws_regions.get())

    except botocore.exceptions.NoCredentialsError as e:
        logger.info("botocore.exceptions.NoCredentialsError in regions()")
        return redirect("/credentials?redirect=/regions")
    except botocore.exceptions.BotoCoreError as e:
        logger.info("botocore.exceptions.BotoCoreError in regions()")
        if e.response['Error']['Code'] == 'AuthError':
            return redirect("/credentials?redirect=/regions")
        return render_template(
            'error.html',
            code=500,
            name="API Error",
            description=e
        )
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'AuthFailure':
            return redirect("/credentials?redirect=/regions")
        else:
            return render_template(
                'error.html',
                code=500,
                name="API Error",
                description="ClientError error: %s" % e
            )
    except Exception as e:
        logger.info("Python exception in regions()")
        return render_template(
            'error.html',
            code=500,
            name="Python Exception",
            description="Unexpected error: %s" % e
        )


@app.route('/', methods=['GET'])
def home_page():
    """
    Show homepage
    """
    return render_template('index.html', redirect="/regions")


@app.route('/<region>/stream/<option>/<path:arn>/', methods=['GET'])
def stream_page(option, arn, region):
    """
    Show details about stream
    """
#    if 'AWS_ACCESS_KEY_ID' not in session:
#        return redirect("/credentials?redirect=" + request.url,code=401)

    span_active = 'active'
    ui = {'details': '', 'count': ''}
    logger.info("arn: {}".format(arn))
    stream_dict = get_slow_query_streams(region)
    start_timestamp = 0
    end_timestamp = 0
    start_date_timestamp = 0
    end_date_timestamp = 0
    date_format_string = "%Y/%m/%d %H:%M:%S"

    if "startDateString" in request.args:
        start_date_string = request.args["startDateString"]
        try:
            start_date_timestamp = int(datetime.datetime.strptime(
                start_date_string,
                date_format_string
                ).timestamp() * 1000)
        except ValueError:
            logger.info("Invalid startDateString '{}' expected '{}'".format(start_date_string, date_format_string))
    else:
        logger.info("startDateString NOT IN URL")

    if "endDateString" in request.args:
        end_date_string = request.args["endDateString"]
        try:
            end_date_timestamp = int(datetime.datetime.strptime(end_date_string, date_format_string).timestamp() * 1000)
        except ValueError:
            logger.info("Invalid endDateString '{}' expected '{}'".format(end_date_string, date_format_string))
    else:
        logger.info("endDateString NOT IN URL")

    if arn in stream_dict:
        stream = stream_dict[arn]
        if option == "details":
            ui['details'] = span_active
            return render_template(
                'stream.html',
                stream=stream,
                ui=ui,
                os=os,
                region=region
            )

        if 'lastEventTimestamp' in stream:
            start_timestamp = stream['lastEventTimestamp'] - (1000 * 60 * 5)
            end_timestamp = stream['lastEventTimestamp']
            # was a startDate specified in the URL?
            if start_date_timestamp:
                logger.info("startDateTimestamp specified in URL: {}".format(start_date_timestamp))
                if start_date_timestamp < stream['firstEventTimestamp']:
                    logger.info("start_timestamp is before the first event in this stream, resetting to first event")
                    start_timestamp = stream['firstEventTimestamp']
                else:
                    start_timestamp = start_date_timestamp
                if start_date_timestamp > stream['lastEventTimestamp']:
                    logger.info(
                        "start_timestamp is after the last event in this stream," +
                        "resetting to last event -1 minute"
                    )
                    start_timestamp = stream['lastEventTimestamp'] - (1000 * 60)
            logger.info("start_timestamp: {}".format(start_timestamp))
            # was an endDate specified in the URL?
            if end_date_timestamp:
                logger.info("endDateTimestamp specified in URL: {}".format(end_date_timestamp))
                if end_date_timestamp > stream['lastEventTimestamp']:
                    logger.info("end_timestamp is after the last event in this stream, resetting to last event")
                    end_timestamp = stream['lastEventTimestamp']
                else:
                    end_timestamp = end_date_timestamp
            if end_timestamp < start_timestamp:
                logger.info(
                    "end_timestamp is actually before start_timestamp: {} < {}".format(
                        end_timestamp,
                        start_timestamp
                    )
                )
                logger.info("Adjusting end_timestamp to one minute after start_timestamp")
                end_timestamp = start_timestamp + (1000 * 60)
            logger.info("end_timestamp: {}".format(end_timestamp))

        if option == "refresh":
            cache_lock.acquire_lock()
            g.logStreamsCache.close()
            g.logStreamsCache = None
            cache_lock.release_lock()
            clear_cache_log_entries(stream['logStreamName'])

            return redirect("/{}/streams/".format(region), code=302)

        if option == "data":
            ui['count'] = span_active
            if 'lastEventTimestamp' in stream:
                log_entries = LogEntries.get_log_entries(
                    g,
                    region,
                    session,
                    logger,
                    stream['logGroup'],
                    stream['logStreamName'],
                    start_timestamp,
                    end_timestamp,
                    cache_lock
                )
                if log_entries.get_count() > 0:
                    oldest_timestamp = log_entries.get_oldest_ts()
                    newest_timestamp = log_entries.get_newest_ts()
                    logger.info("oldestTimestamp: {} {}".format(
                        oldest_timestamp,
                        datetime.datetime.fromtimestamp(oldest_timestamp/1000.0)
                        )
                    )
                    logger.info("newestTimestamp: {} {}".format(
                        newest_timestamp,
                        datetime.datetime.fromtimestamp(newest_timestamp/1000.0)
                        )
                    )
                    return render_template(
                        'stream_data.html',
                        stream=stream,
                        ui=ui,
                        dataset=log_entries.get_queries_as_json(),
                        metrics=log_entries.get_metrics(),
                        os=os,
                        start_timestamp=oldest_timestamp,
                        end_timestamp=newest_timestamp,
                        region=region
                    )
                else:
                    logger.info("No data returned for arn: {}, in this time window".format(arn))
                    return render_template(
                        'stream_data.html',
                        stream=stream,
                        ui=ui,
                        metrics={},
                        logEntries={},
                        os=os,
                        start_timestamp=start_timestamp,
                        end_timestamp=end_timestamp,
                        region=region
                    )

    logger.info("arn: {} NOT FOUND, returning 404".format(arn))
    abort(404)


@app.route('/<region>/streams/', methods=['GET'])
def streamlist_page(region):
    """
    Show list of known Clusters
    """

    stream_dict = get_slow_query_streams(region)
    stream_list = []
    for arn in sorted(stream_dict):
        stream_list.append(stream_dict[arn])
    logger.info("List length: {}".format(len(stream_list)))
    return render_template(
        'streams.html',
        streamList=stream_list,
        region=region
    )


def get_slow_query_streams(region):
    # Actually hold the lock until we are done with this function...
    cache_lock.acquire_lock()

    if region in g.logStreamsCache:
        if 'lastModifiedTime' in g.logStreamsCache[region]:
            if g.logStreamsCache[region]['lastModifiedTime'] > LogEntries.oldest_viable_cache_timestamp():
                temp_ls = g.logStreamsCache[region]['logStreams']
                cache_lock.release_lock()
                return temp_ls

    log_groups = describe_log_groups(region)

    all_log_streams = {}
    for logGroup in log_groups:
        if "slowquery" not in logGroup['logGroupName']:
            continue
        logger.info('Group: {}'.format(logGroup['logGroupName']))

        log_streams = describe_log_streams(region, logGroup['logGroupName'])

        all_log_streams.update(log_streams)
        logger.debug('Streams: {}'.format(log_streams))

    g.logStreamsCache[region] = {}
    g.logStreamsCache[region]['lastModifiedTime'] = time.time() * 1000
    g.logStreamsCache[region]['logStreams'] = all_log_streams

    cache_lock.release_lock()

    return all_log_streams


def clear_cache_log_entries(log_stream_name):
    cache_lock.acquire_lock()
    if log_stream_name in g.logEntriesCache:
        del g.logEntriesCache[log_stream_name]
    cache_lock.release_lock()


def describe_log_streams(region, log_group_name_value):
    if 'logs_client' not in g:
        g.logs_client = {}
        if region not in g.logs_client:
            g.logs_client.region = boto3.client(
                'logs',
                aws_access_key_id=session['AWS_ACCESS_KEY_ID'],
                aws_secret_access_key=session['AWS_SECRET_ACCESS_KEY'],
                region_name=region
            )

    log_streams = {}

    response = g.logs_client[region].describe_log_streams(logGroupName=log_group_name_value)
    for elem in response['logStreams']:
        elem['logGroup'] = log_group_name_value
        log_streams[elem['arn']] = elem
    while 'nextToken' in response:
        response = g.logs_client[region].describe_log_streams(
            logGroupName=log_group_name_value,
            nextToken=response['nextToken']
        )

        for elem in response['logStreams']:
            elem['logGroup'] = log_group_name_value
            log_streams[elem['arn']] = elem
    logger.info('LogStreams Found: {}'.format(len(log_streams)))
    return log_streams


def describe_log_groups(region):
    if 'logs_client' not in g:
        g.logs_client = {}
        if region not in g.logs_client:
            g.logs_client[region] = boto3.client(
                'logs',
                aws_access_key_id=session['AWS_ACCESS_KEY_ID'],
                aws_secret_access_key=session['AWS_SECRET_ACCESS_KEY'],
                region_name=region
            )

    response = g.logs_client[region].describe_log_groups(logGroupNamePrefix='/aws/rds/instance', limit=10)
    log_groups = response['logGroups']
    while 'nextToken' in response:
        response = g.logs_client[region].describe_log_groups(
            logGroupNamePrefix='/aws/rds/instance',
            nextToken=response['nextToken']
        )

        log_groups = log_groups + response['logGroups']
    logger.info('LogGroups Found: {}'.format(len(log_groups)))
    return log_groups


@app.template_filter('urlencode')
def urlencode_filter(s):
    if type(s) == 'Markup':
        s = s.unescape()
    s = s.encode('utf8')
    s = urllib.parse.quote_plus(s)
    return Markup(s)


@app.template_filter('tsconvert')
def ts_to_string(s):
    if isinstance(s, int):
        possible_ts = s
        # After 1/1/2018 and before 1/1/2050
        if 1514764800000 < possible_ts < 2524608000000:
            s = "{} [ {} ]".format(
                datetime.datetime.fromtimestamp(possible_ts/1000.0),
                possible_ts
            )
    return Markup(s)


def start_https():
    global web_protocol
    web_protocol = "HTTPS"
    global cache_lock
    cache_lock = CacheLock(logger, g, session, web_protocol)

    app.secret_key = 'does this really matter?'
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = False

    logger.info('Starting HTTPS server...')
    if "DEBUG" in os.environ:
        app.run(ssl_context=('ssl/server.pem', 'ssl/key.pem'), debug=True, host='0.0.0.0', port=5151)
    else:
        app.run(ssl_context=('ssl/server.pem', 'ssl/key.pem'), host='0.0.0.0', port=5151)
    logger.info('HTTPS Exiting...')
    exit(0)


if __name__ == '__main__':
    start_https()
    logger.info('Exiting...')
