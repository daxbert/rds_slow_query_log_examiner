from __future__ import unicode_literals
from multiprocessing import Process, Lock
from flask import Flask, request, redirect, abort, render_template, g
import botocore
import time
import logging
import datetime
import boto3
import re
import os
import shelve
import urllib
from markupsafe import Markup
# import our local classes
from sql import SQL

os.environ["AWS_DEFAULT_REGION"] = "us-west-2"

MAX_QUERIES_TO_PARSE = 20000
MAX_QUERIES_TO_APPEND = 10

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


cacheLock = None  # used to avoid concurrent access to the cache...
web_protocol = ""


def acquire_lock():
    logger.info("Acquiring Lock... {}".format(web_protocol))
    cacheLock.acquire()
    logger.info("Opening Cache")
    g.logEntriesCache = shelve.open("logEntriesCache.data", writeback=True)
    g.logStreamsCache = shelve.open("logStreamsCache.data", writeback=True)
    logger.info("{}".format(g.logEntriesCache))
    logger.info("{}".format(g.logStreamsCache))
    logger.info("Acquired {}".format(web_protocol))


def release_lock():
    logger.info("Release Lock...{}".format(web_protocol))
    g.logEntriesCache.close()
    g.logStreamsCache.close()
    cacheLock.release()
    logger.debug("Released {}".format(web_protocol))


@app.route('/regions', methods=['GET'])
def regions():
    """
    Show Region List
    """
    client = boto3.client('ec2')

    try:
        response = client.describe_regions()

        return render_template('regions.html', response=response)

    except botocore.exceptions.NoCredentialsError as e:
        logger.info("botocore.exceptions.NoCredentialsError in regions()")
        return render_template(
            'error.html',
            code=500,
            name="No AWS Credentials Provided. You need to " +
                 "set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY " +
                 "on the docker command line",
            description=e
        )

    except botocore.exceptions.BotoCoreError as e:
        logger.info("botocore.exceptions.BotoCoreError in regions()")
        return render_template(
            'error.html',
            code=500,
            name="API Error",
            description=e
        )

    except Exception as e:
        logger.info("Python exception in regions()")
        return render_template(
            'error.html',
            code=500,
            name="Python Exception",
            description=e
        )


@app.route('/', methods=['GET'])
def home_page():
    """
    Show homepage
    """
    return render_template('index.html', redirect="/regions")


"""
regex patterns used in the parse_log_entry function
"""

regexPerformance = re.compile(
    r"^# Query_time:\s+(\d+\.\d+)\s+Lock_time:\s+(\d+\.\d+)\s+Rows_sent:\s+(\d+)\s+Rows_examined:\s+(\d+)"
)

regexUserInfo = re.compile(
    r"^# User@Host:\s+(\S+)\s+@\s+(.*)\s+Id:\s+(\d+)"
)

regexLinesToIgnore = [
    re.compile(r"^#"),
    re.compile(r"^use ", re.I),
    re.compile(r"^set ", re.I)
]


def skip_line(line):
    for regex in regexLinesToIgnore:
        if bool(regex.match(line)):
            logger.debug("IGNORE: {}".format(line))
            return True
    return False


def parse_log_entry(cw_event):
    query = None
    query_time = None
    lock_time = None
    sent = None
    rows = None
    host = None
    user = None
    session = None
    for line in cw_event['message'].splitlines():
        logger.debug("LINE: {}".format(line))
        user_info = regexUserInfo.match(line)
        if user_info:
            query = ""
            user = user_info.group(1)
            host = user_info.group(2)
            session = user_info.group(3)
            continue

        if bool(re.match('^# Query_time:', line)):
            query = ""
            logger.debug("QT LIKELY: {}".format(line))
            m = regexPerformance.match(line)
            if m:
                query_time = float(m.group(1))
                lock_time = float(m.group(2))
                sent = int(m.group(3))
                rows = int(m.group(4))
                logger.debug("QT OK: {} {}".format(query_time, rows))
            else:
                logger.debug("QT ERROR: {}".format(line))
            continue

        if skip_line(line):
            continue

        query = query + line + "\t"

    # done with the entry... do we have a pending query to output
    if any(x is None for x in [rows, query_time, lock_time, user, host]):
        logger.info("PARSE_FAILED: {}".format(cw_event))
        logger.info("PARSE_FAILED: {} {} {} {} {}".format(
                rows,
                query_time,
                lock_time,
                user,
                host
            )
        )
    return {
        'event': cw_event,
        'qtime': query_time,
        'session': session,
        'rows': rows,
        'sent': sent,
        'ltime': lock_time,
        'query': query,
        'raw': cw_event['message'],
        'timestamp': cw_event['timestamp']
    }


@app.route('/<region>/stream/<option>/<path:arn>/', methods=['GET'])
def stream_page(option, arn, region):
    """
    Show details about stream
    """
    os.environ['AWS_DEFAULT_REGION'] = region
    span_active = 'active'
    ui = {'details': '', 'count': ''}
    logger.info("arn: {}".format(arn))
    stream_dict = get_slow_query_streams()
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
            return render_template('stream.html', stream=stream, ui=ui, os=os)

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
            acquire_lock()
            g.logStreamsCache.close()
            g.logStreamsCache = None
            release_lock()
            clear_cache_log_entries(stream['logStreamName'])

            return redirect("/{}/streams/".format(region), code=302)

        if option == "data":
            ui['count'] = span_active
            if 'lastEventTimestamp' in stream:
                log_entries = get_log_entries(stream['logGroup'], stream['logStreamName'], start_timestamp, end_timestamp)
                if 'METRICS' in log_entries:
                    oldest_timestamp = log_entries['METRICS']['FIRST_TS']
                    newest_timestamp = log_entries['METRICS']['LAST_TS']
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
                        metrics=log_entries['METRICS'],
                        logEntries=log_entries['QUERIES'],
                        os=os,
                        start_timestamp=oldest_timestamp,
                        end_timestamp=newest_timestamp
                    )
                else:
                    logger.info("No data returned for arn: {}, in this time window".format(arn))
                    return render_template('stream_data.html',
                                           stream=stream,
                                           ui=ui,
                                           metrics={},
                                           logEntries={},
                                           os=os,
                                           start_timestamp=start_timestamp,
                                           end_timestamp=end_timestamp
                                           )

    logger.info("arn: {} NOT FOUND, returning 404".format(arn))
    abort(404)


@app.route('/<region>/streams/', methods=['GET'])
def streamlist_page(region):
    """
    Show list of known Clusters
    """
    os.environ['AWS_DEFAULT_REGION'] = region
    stream_dict = get_slow_query_streams()
    stream_list = []
    for arn in sorted(stream_dict):
        stream_list.append(stream_dict[arn])
    logger.info("List length: {}".format(len(stream_list)))
    return render_template(
        'streams.html',
        streamList=stream_list,
        region=region
    )


def oldest_viable_cache_timestamp():
    # 1 Hour ago...
    return (time.time() * 1000) - (60 * 60 * 1000)


def get_slow_query_streams():
    # Actually hold the lock until we are done with this function...
    acquire_lock()

    region = os.environ['AWS_DEFAULT_REGION']
    if region in g.logStreamsCache:
        if 'lastModifiedTime' in g.logStreamsCache[region]:
            if g.logStreamsCache[region]['lastModifiedTime'] > oldest_viable_cache_timestamp():
                temp_ls = g.logStreamsCache[region]['logStreams']
                release_lock()
                return temp_ls

    log_groups = describe_log_groups()

    all_log_streams = {}
    for logGroup in log_groups:
        if "slowquery" not in logGroup['logGroupName']:
            continue
        logger.info('Group: {}'.format(logGroup['logGroupName']))

        log_streams = describe_log_streams(logGroup['logGroupName'])

        all_log_streams.update(log_streams)
        logger.debug('Streams: {}'.format(log_streams))

    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']] = {}
    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['lastModifiedTime'] = time.time() * 1000
    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['logStreams'] = all_log_streams

    release_lock()

    return all_log_streams


def clear_cache_log_entries(log_stream_name):
    acquire_lock()
    if log_stream_name in g.logEntriesCache:
        del g.logEntriesCache[log_stream_name]
    release_lock()


def update_log_entries(log_entries, new_entry):
    if 'QUERIES' not in log_entries:
        log_entries['QUERIES'] = {}
        log_entries['METRICS'] = {}

    if new_entry['hash'] in log_entries['QUERIES']:
        existing_entry = log_entries['QUERIES'][new_entry['hash']]
        if len(existing_entry['queries']) < MAX_QUERIES_TO_APPEND:
            existing_entry['queries'].append(new_entry)
            logger.debug("LEN: {}".format(len(existing_entry['queries'])))
        existing_entry['totalcount']  += 1
        existing_entry['totalrows']   += int(new_entry['rows'])
        existing_entry['totalsent']   += int(new_entry['sent'])
        existing_entry['totalqtime']  += float(new_entry['qtime'])
        existing_entry['totalltime']  += float(new_entry['ltime'])
        for metric in ("sent", "rows", "qtime", "ltime"):
            if new_entry[metric] > existing_entry['slowest'][metric][metric]:
                existing_entry['slowest'][metric] = new_entry
    else:
        log_entries['QUERIES'][new_entry['hash']] = {
            'queries': [new_entry],
            'slowest': {'sent': new_entry, 'rows': new_entry, 'qtime': new_entry, 'ltime': new_entry},
            'totalcount': 1,
            'hash': new_entry['hash'],
            'totalsent': int(new_entry['sent']),
            'totalrows': int(new_entry['rows']),
            'totalqtime': float(new_entry['qtime']),
            'totalltime': float(new_entry['ltime'])
        }

    if 'TOTAL_QUERY_COUNT' in log_entries['METRICS']:
        log_entries['METRICS']['TOTAL_QUERY_COUNT'] += 1
        log_entries['METRICS']['TOTAL_ROWS'] += int(new_entry['rows'])
        log_entries['METRICS']['TOTAL_SENT'] += int(new_entry['sent'])
        log_entries['METRICS']['TOTAL_QTIME'] += float(new_entry['qtime'])
        log_entries['METRICS']['TOTAL_LTIME'] += float(new_entry['ltime'])
        ts = new_entry['event']['timestamp']
        if ts < log_entries['METRICS']['FIRST_TS']:
            log_entries['METRICS']['FIRST_TS'] = ts
        if ts > log_entries['METRICS']['LAST_TS']:
            log_entries['METRICS']['LAST_TS'] = ts
    else:
        log_entries['METRICS']['TOTAL_QUERY_COUNT'] = 1
        log_entries['METRICS']['FIRST_TS'] = new_entry['event']['timestamp']
        log_entries['METRICS']['LAST_TS'] = new_entry['event']['timestamp']
        log_entries['METRICS']['TOTAL_ROWS'] = int(new_entry['rows'])
        log_entries['METRICS']['TOTAL_SENT'] = int(new_entry['sent'])
        log_entries['METRICS']['TOTAL_QTIME'] = float(new_entry['qtime'])
        log_entries['METRICS']['TOTAL_LTIME'] = float(new_entry['ltime'])

    return log_entries


def process_cloudwatch_response(response, log_entries, log_stream_name):
    logger.info("Event Count: {}".format(len(response['events'])))
    if len(response['events']) > 0:
        first_ts = response['events'][0]['timestamp']
        last_ts = response['events'][len(response['events']) - 1]['timestamp']
        if last_ts < first_ts:
            first_ts, last_ts = last_ts, first_ts
        logger.info("Stream: {} from {} to {}".format(
            log_stream_name,
            datetime.datetime.fromtimestamp(first_ts/1000.0),
            datetime.datetime.fromtimestamp(last_ts / 1000.0)))
        for event in response['events']:
            le = parse_log_entry(event)
            if le is None:
                return log_entries
            temp_query = SQL(le['query'])
            le['hash'] = temp_query.fingerprint()
            log_entries = update_log_entries(log_entries, le)
        return log_entries, len(response['events'])
    else:
        return log_entries, 0


def get_log_entries(log_group, log_stream_name, start_time, end_time):
    key = log_stream_name + "_" + str(start_time) + "_" + str(end_time)
    logger.info("Key: {}".format(key))

    acquire_lock()
    if key in g.logEntriesCache:
        if g.logEntriesCache[key]['lastModifiedTime'] > oldest_viable_cache_timestamp():
            temp_array = (
                g.logEntriesCache[key]['logEntries'],
                g.logEntriesCache[key]['oldestTimestamp'],
                g.logEntriesCache[key]['newestTimestamp']
            )
            release_lock()
            return temp_array
    release_lock()

    log_entries = {}
    budget_left = MAX_QUERIES_TO_PARSE
    client = boto3.client('logs')

    response = client.get_log_events(
        logGroupName=log_group,
        logStreamName=log_stream_name,
        startTime=start_time,
        endTime=end_time,
        startFromHead=False
    )

    log_entries, count = process_cloudwatch_response(response, log_entries, log_stream_name)
    budget_left = budget_left - count
    logger.info("Budget Left: {}".format(budget_left))

    while budget_left > 0 and count > 0:
        response = client.get_log_events(
            logGroupName=log_group,
            logStreamName=log_stream_name,
            startTime=start_time,
            endTime=end_time,
            startFromHead=False,
            nextToken=response['nextBackwardToken']
        )

        log_entries, count = process_cloudwatch_response(response, log_entries, log_stream_name)
        budget_left = budget_left - count
        logger.info("Budget Left: {}".format(budget_left))

    acquire_lock()

    if 'METRICS' in log_entries:
        logger.info('TOTAL Queries Parsed: {}'.format(log_entries['METRICS']['TOTAL_QUERY_COUNT']))
        logger.info('TOTAL Deduped SQL Found: {}'.format(len(log_entries['QUERIES'])))
        key = log_stream_name + \
            "_" + \
            str(log_entries['METRICS']['FIRST_TS']) + \
            "_" + \
            str(log_entries['METRICS']['LAST_TS'])
        logger.info("Key: {}".format(key))
        g.logEntriesCache[key] = {
            'logEntries': log_entries,
            'lastModifiedTime': time.time() * 1000,
            'oldestTimestamp': log_entries['METRICS']['FIRST_TS'],
            'newestTimestamp': log_entries['METRICS']['LAST_TS'],
        }
    else:
        #  logEntries has no METRICS.. and therefore no entries
        #  update cache for startTime, endTime as this will
        #  be a "negative" cache
        g.logEntriesCache[key] = {
            'logEntries': log_entries,
            'lastModifiedTime': time.time() * 1000,
            'oldestTimestamp': start_time,
            'newestTimestamp': end_time,
            }

    release_lock()

    return log_entries


def describe_log_streams(log_group_name_value):
    client = boto3.client('logs')
    log_streams = {}

    response = client.describe_log_streams(logGroupName=log_group_name_value)
    for elem in response['logStreams']:
        elem['logGroup'] = log_group_name_value
        log_streams[elem['arn']] = elem
    while 'nextToken' in response:
        response = client.describe_log_streams(logGroupName=log_group_name_value, nextToken=response['nextToken'])

        for elem in response['logStreams']:
            elem['logGroup'] = log_group_name_value
            log_streams[elem['arn']] = elem
    logger.info('LogStreams Found: {}'.format(len(log_streams)))
    return log_streams


def describe_log_groups():
    client = boto3.client('logs')

    response = client.describe_log_groups(logGroupNamePrefix='/aws/rds/instance', limit=10)
    log_groups = response['logGroups']
    while 'nextToken' in response:
        response = client.describe_log_groups(logGroupNamePrefix='/aws/rds/instance', nextToken=response['nextToken'])

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


def start_http():
    global lockAcquired
    global web_protocol
    lockAcquired = False
    web_protocol = "HTTP"

    logger.info('Starting HTTP server...')
    if "DEBUG" in os.environ:
        app.run(debug=True, host='0.0.0.0', port=5150)
    else:
        app.run(host='0.0.0.0', port=5150)
    logger.info('HTTP Exiting...')
    exit(0)


def start_https():
    global lockAcquired
    global web_protocol
    lockAcquired = False
    web_protocol = "HTTPS"
    logger.info('Starting HTTPS server...')
    if "DEBUG" in os.environ:
        app.run(ssl_context='adhoc', debug=True, host='0.0.0.0', port=5151)
    else:
        app.run(ssl_context='adhoc', host='0.0.0.0', port=5151)
    logger.info('HTTPS Exiting...')
    exit(0)


if __name__ == '__main__':
    # This starts the built in flask server, not designed for production use
    logger.info('Init Lock Object')
    cacheLock = Lock()
    lockAcquired = False

    logger.info('Setting up two processes for HTTP/HTTPS')
    p1 = Process(target=start_http)
    p1.start()
    p2 = Process(target=start_https)
    p2.start()
    p1.join()
    p2.join()
    logger.info('Exiting...')
