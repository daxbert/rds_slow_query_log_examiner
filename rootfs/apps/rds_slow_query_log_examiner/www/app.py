from __future__ import unicode_literals
from multiprocessing import Process, Lock
from flask import Flask, request, redirect, jsonify, abort, render_template,  g
# from werkzeug.exceptions import NotFound
from sql import SQL
import botocore
import time
import logging
import datetime
import copy
import boto3
#import settings
import re
import pprint
import os
import shelve
os.environ["AWS_DEFAULT_REGION"] = "us-west-2"

MAX_QUERIES_TO_PARSE=20000
MAX_QUERIES_TO_APPEND=10

app = Flask(__name__)

logger = logging.getLogger('rds_slow_query_log_examiner')
logger.setLevel('INFO')
logger.propagate = False
stderr_logs = logging.StreamHandler()
stderr_logs.setLevel('INFO')
stderr_logs.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(stderr_logs)

cacheLock = Lock() # used to avoid concurrent access to the cache...
lockAcquired = None

def acquireLock():
    global lockAcquired
    if lockAcquired:
        logger.debug("Acquiring existing lock: NOP")
    else:
        logger.debug("Acquiring Lock...")
        lockAcquired = True
        cacheLock.acquire()
        logger.debug("Acquired")

def releaseLock():
    global lockAcquired

    if lockAcquired:
        logger.debug("Release Lock...")
        lockAcquired = False
        cacheLock.release()
        logger.debug("Released")
    else:
        logger.debug("Releasing non-existant lock: NOP")

@app.before_request
def before_req():
    acquireLock()
    logger.info("Opening Cache")
    g.logEntriesCache = shelve.open("logEntriesCache.data",writeback=True)
    g.logStreamsCache = shelve.open("logStreamsCache.data",writeback=True)
    logger.info("{}".format(g.logEntriesCache))
    logger.info("{}".format(g.logStreamsCache))

@app.after_request
def after_req(response):
    logger.info("Closing Cache")
    g.logEntriesCache.close()
    if ( g.logStreamsCache is None):
        os.remove("logStreamsCache.data")
    else:
        g.logStreamsCache.close()
    releaseLock()
    return response


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
        return render_template('error.html', code = 500, name = "No AWS Credentials Provided.  You need to set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY on the docker command line", description = e)

    except botocore.exceptions.BotoCoreError as e:
        return render_template('error.html', code = 500, name = "API Error", description = e)

    except Error as e:
        logger.info("Exception by boto")
        return render_template('error.html', code = 500, name = "Python Exception", description = e)

    return None

@app.route('/', methods=['GET'])
def home_page():
    """
    Show homepage
    """
    return render_template('index.html', redirect="/regions")

"""
regex patterns used in the parseLogEntry function
"""

regexPerformance = re.compile(r"^# Query_time:\s+(\d+\.\d+)\s+Lock_time:\s+(\d+\.\d+)\s+Rows_sent:\s+(\d+)\s+Rows_examined:\s+(\d+)")

regexUserInfo= re.compile(r"^# User@Host:\s+(\S+)\s+@\s+(.*)\s+Id:\s+(\d+)")

regexLinestoIgnore = [ re.compile(r"^#"), re.compile(r"^use ", re.I ), re.compile(r"^set ", re.I) ]


def skipLine(line):
    for regex in regexLinestoIgnore:
        if ( bool(regex.match(line))):
            logger.debug("IGNORE: {}".format(line))
            return True
    return False

def parseLogEntry(cw_event):
    query = None
    qtime = None
    ltime = None
    sent = None
    rows = None
    host = None
    user = None
    session = None
    for line in cw_event['message'].splitlines():
        logger.debug("LINE: {}".format(line))
        userinfo = regexUserInfo.match(line)
        if ( userinfo ):
            query = ""
            user = userinfo.group(1)
            host = userinfo.group(2)
            session = userinfo.group(3)
            continue

        if ( bool(re.match('^# Query_time:' , line))):
            query = ""
            logger.debug("QT LIKELY: {}".format(line))
            m = regexPerformance.match(line)
            if ( m ):
                qtime = float(m.group(1))
                ltime = float(m.group(2))
                sent = int(m.group(3))
                rows = int(m.group(4))
                logger.debug("QT OK: {} {}".format(qtime, rows))
            else:
                logger.debug("QT ERROR: {}".format(line))
            continue

        if ( skipLine(line) ):
            continue

        query = query + line + "\t";

    # done with the entry... do we have a pending query to output
    if any(x is None for x in [rows,qtime,ltime,user,host]):
        logger.info("PARSE_FAILED: {}".format(cw_event))
        logger.info("PARSE_FAILED: {} {} {} {} {}".format(rows,qtime,ltime,user,host))
    return { 'event': cw_event, 'qtime': qtime, 'session': session, 'rows': rows, 'sent': sent, 'ltime': ltime, 'query': query, 'raw': cw_event['message'], 'timestamp': cw_event['timestamp'] }

@app.route('/<region>/stream/<option>/<path:arn>/', methods=['GET'])
def stream_page(option, arn, region):
    """
    Show details about stream
    """
    os.environ['AWS_DEFAULT_REGION'] = region
    spanActive = 'active'
    ui = { 'details': '', 'count': '' }
    logger.info("arn: {}".format(arn))
    streamDict = getSlowQueryStreams()
    start_timestamp = 0
    end_timestamp = 0
    startDateTimestamp = 0
    endDateTimestamp = 0
    dateFormatString = "%Y/%m/%d %H:%M:%S"

    if "startDateString" in request.args:
        startDateString = request.args["startDateString"]
        try:
            startDateTimestamp = int(datetime.datetime.strptime(startDateString, dateFormatString).timestamp() * 1000)
        except ValueError:
            logger.info("Invalid startDateString '{}' expected '{}'".format(startDateString, dateFormatString))
    else:
        logger.info("startDateString NOT IN URL")

    if "endDateString" in request.args:
        endDateString = request.args["endDateString"]
        try:
            endDateTimestamp = int(datetime.datetime.strptime(endDateString, dateFormatString).timestamp() * 1000)
        except ValueError:
            logger.info("Invalid endDateString '{}' expected '{}'".format(endDateString,dateFormatString))
    else:
        logger.info("endDateString NOT IN URL")

    if arn in streamDict:
        stream = streamDict[arn]
        if ( option == "details" ):
            ui['details'] = spanActive
            return render_template('stream.html', stream = stream, ui = ui, os = os )

        if 'lastEventTimestamp' in stream:
            start_timestamp = stream['lastEventTimestamp'] - ( 1000 * 60 * 5 )
            end_timestamp = stream['lastEventTimestamp']
            # was a startDate specified in the URL?
            if ( startDateTimestamp ):
                logger.info("startDateTimestamp specified in URL: {}".format(startDateTimestamp))
                if ( startDateTimestamp < stream['firstEventTimestamp'] ):
                    logger.info("start_timestamp is before the first event in this stream, resetting to first event")
                    start_timestamp = stream['firstEventTimestamp']
                else:
                    start_timestamp = startDateTimestamp
                if (startDateTimestamp > stream['lastEventTimestamp']):
                    logger.info("start_timestamp is after the last event in this stream, resetting to last event -1 minute")
                    start_timestamp = stream['lastEventTimestamp'] - ( 1000 * 60 )
            logger.info("start_timestamp: {}".format(start_timestamp))
            # was an endDate specified in the URL?
            if ( endDateTimestamp ):
                logger.info("endDateTimestamp specified in URL: {}".format(endDateTimestamp))
                if ( endDateTimestamp > stream['lastEventTimestamp'] ):
                    logger.info("end_timestamp is after the last event in this stream, resetting to last event")
                    end_timestamp = stream['lastEventTimestamp']
                else:
                    end_timestamp = endDateTimestamp
            if ( end_timestamp < start_timestamp ):
                logger.info("end_timestamp is actually before start_timestamp: {} < {}".format(end_timestamp,start_timestamp))
                logger.info("Adjusting end_timestamp to one minute after start_timestamp")
                end_timestamp = start_timestamp + (1000 * 60)
            logger.info("end_timestamp: {}".format(end_timestamp))

        if ( option == "refresh" ):
            g.logStreamsCache.close()
            g.logStreamsCache = None
            clearCacheLogEntries(stream['logGroup'], stream['logStreamName'], start_timestamp, end_timestamp)
            return redirect("/{}/streams/".format(region), code=302)

        logEntries = {}

        if ( option == "data" ):
            ui['count'] = spanActive
            if 'lastEventTimestamp' in stream:
                logEntries = getLogEntries(stream['logGroup'], stream['logStreamName'], start_timestamp, end_timestamp)
                if 'METRICS' in logEntries:
                    oldestTimestamp=logEntries['METRICS']['FIRST_TS']
                    newestTimestamp=logEntries['METRICS']['LAST_TS']
                    logger.info("oldestTimestamp: {} {}".format(oldestTimestamp, datetime.datetime.fromtimestamp(oldestTimestamp/1000.0)))
                    logger.info("newestTimestamp: {} {}".format(newestTimestamp, datetime.datetime.fromtimestamp(newestTimestamp/1000.0)))
                    return render_template('stream_data.html',
                                           stream = stream,
                                           ui = ui,
                                           metrics = logEntries['METRICS'],
                                           logEntries = logEntries['QUERIES'],
                                           os = os,
                                           start_timestamp = oldestTimestamp,
                                           end_timestamp = newestTimestamp
                                           )
                else:
                    logger.info("No data returned for arn: {}, in this time window".format(arn))
                    return render_template('stream_data.html',
                                           stream=stream,
                                           ui=ui,
                                           metrics={},
                                           logEntries= {},
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
    streamDict = getSlowQueryStreams()
    streamList = []
    for arn in sorted(streamDict):
        streamList.append(streamDict[arn])
    logger.info("List length: {}".format(len(streamList)))
    return render_template('streams.html', streamList = streamList, region = region )

def oldestViableCacheTimestamp():
   # 5 minutes ago...
   return ( ( time.time() * 1000 ) - (5 * 60 * 1000 ))

def getSlowQueryStreams():
    if ( os.environ['AWS_DEFAULT_REGION'] in g.logStreamsCache ):
        if ( 'lastModifiedTime' in g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]):
            if ( g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['lastModifiedTime'] > oldestViableCacheTimestamp()):
                return g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['logStreams']

    releaseLock()
    logGroups = describeLogGroups()
    acquireLock()

    allLogStreams = {}
    for logGroup in logGroups:
        if "slowquery" not in logGroup['logGroupName']:
            continue
        logger.info('Group: {}'.format(logGroup['logGroupName']))

        releaseLock()
        logStreams = describeLogStreams(logGroup['logGroupName'])
        acquireLock()

        allLogStreams.update(logStreams)
        logger.debug('Streams: {}'.format(logStreams))
    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']] = {}
    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['lastModifiedTime'] = time.time() * 1000
    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['logStreams'] = allLogStreams
    return g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['logStreams']

def clearCacheStreamEntries(logGroup, logStreamName, startTime, endTime):
    if logStreamName in g.logEntriesCache:
        del g.logEntriesCache[logStreamName]

def clearCacheLogEntries(logGroup, logStreamName, startTime, endTime):
    if logStreamName in g.logEntriesCache:
        del g.logEntriesCache[logStreamName]

def updateLogEntries(logEntries,le):
    if not 'QUERIES' in logEntries:
        logEntries['QUERIES'] = {}
        logEntries['METRICS'] = {}

    if le['hash'] in logEntries['QUERIES']:
        leqh = logEntries['QUERIES'][le['hash']]
        if ( len(leqh['queries']) < MAX_QUERIES_TO_APPEND ):
            leqh['queries'].append(le)
            logger.debug("LEN: {}".format(len(leqh['queries'])))
        leqh['totalcount']  += 1
        leqh['totalrows']   += int(le['rows'])
        leqh['totalsent']   += int(le['sent'])
        leqh['totalqtime']  += float(le['qtime'])
        leqh['totalltime']  += float(le['ltime'])
        for metric in ("sent", "rows", "qtime", "ltime"):
            if (le[metric] > leqh['slowest'][metric][metric]):
                leqh['slowest'][metric] = le
    else:
        logEntries['QUERIES'][le['hash']] = {
            'queries': [ le ],
            'slowest': { 'sent': le, 'rows': le, 'qtime': le, 'ltime': le},
            'totalcount' : 1,
            'hash': le['hash'],
            'totalsent' : int(le['sent']),
            'totalrows' : int(le['rows']),
            'totalqtime' : float(le['qtime']),
            'totalltime' : float(le['ltime'])
        }

    if 'TOTAL_QUERY_COUNT' in logEntries['METRICS']:
        logEntries['METRICS']['TOTAL_QUERY_COUNT'] += 1
        logEntries['METRICS']['TOTAL_ROWS']   += int(le['rows'])
        logEntries['METRICS']['TOTAL_SENT']   += int(le['sent'])
        logEntries['METRICS']['TOTAL_QTIME']  += float(le['qtime'])
        logEntries['METRICS']['TOTAL_LTIME']  += float(le['ltime'])
        ts = le['event']['timestamp']
        if ( ts < logEntries['METRICS']['FIRST_TS']):
            logEntries['METRICS']['FIRST_TS'] = ts
        if (ts > logEntries['METRICS']['LAST_TS']):
            logEntries['METRICS']['LAST_TS'] = ts
    else:
        logEntries['METRICS']['TOTAL_QUERY_COUNT'] = 1
        logEntries['METRICS']['FIRST_TS'] = le['event']['timestamp']
        logEntries['METRICS']['LAST_TS'] = le['event']['timestamp']
        logEntries['METRICS']['TOTAL_ROWS'] = int(le['rows'])
        logEntries['METRICS']['TOTAL_SENT'] = int(le['sent'])
        logEntries['METRICS']['TOTAL_QTIME'] = float(le['qtime'])
        logEntries['METRICS']['TOTAL_LTIME'] = float(le['ltime'])

    return logEntries

def processCloudWatchResponse(response, logEntries):
    logger.info("Event Count: {}".format(len(response['events'])))
    if ( len(response['events']) > 0 ):
        first_ts = response['events'][0]['timestamp']
        last_ts = response['events'][len(response['events']) - 1]['timestamp']
        if last_ts < first_ts:
            first_ts,last_ts = last_ts,first_ts
        logger.info("From: {} to {}".format(datetime.datetime.fromtimestamp(first_ts/1000.0),
                                            datetime.datetime.fromtimestamp(last_ts / 1000.0)))
        for event in response['events']:
            le = parseLogEntry(event)
            if le is None:
               return logEntries
            tempquery = SQL(le['query'])
            le['hash'] = tempquery.fingerprint()
            logEntries = updateLogEntries(logEntries, le)
        return logEntries, len(response['events'])
    else:
        return logEntries, 0

def getLogEntries(logGroup, logStreamName, startTime, endTime):
    key = logStreamName + "_" + str(startTime) + "_" + str(endTime)
    logger.info("Key: {}".format(key))
    if key in g.logEntriesCache:
        if g.logEntriesCache[key]['lastModifiedTime'] > oldestViableCacheTimestamp():
            return ( g.logEntriesCache[key]['logEntries'], g.logEntriesCache[key]['oldestTimestamp'], g.logEntriesCache[key]['newestTimestamp'] )
    logEntries = {}
    budgetLeft = MAX_QUERIES_TO_PARSE
    client = boto3.client('logs')

    releaseLock()  # let's not keep the lock when we make the API call...
    response = client.get_log_events(logGroupName = logGroup,logStreamName = logStreamName,startTime = startTime, endTime = endTime,startFromHead=False)
    acquireLock()  # now get the lock back...

    logEntries, tempCount = processCloudWatchResponse(response, logEntries)
    budgetLeft = budgetLeft - tempCount
    logger.info("Budget Left: {}".format(budgetLeft))

    while (budgetLeft > 0 and tempCount > 0):
        releaseLock()  # let's not keep the lock when we make the API call...
        response = client.get_log_events(logGroupName = logGroup,logStreamName = logStreamName, startTime = startTime, endTime = endTime, startFromHead=False, nextToken=response['nextBackwardToken'])
        acquireLock()  # now get the lock back...

        logEntries, tempCount = processCloudWatchResponse(response, logEntries)
        budgetLeft = budgetLeft - tempCount
        logger.info("Budget Left: {}".format(budgetLeft))

    if 'METRICS' in logEntries:
        logger.info('TOTAL Queries Parsed: {}'.format(logEntries['METRICS']['TOTAL_QUERY_COUNT']))
        logger.info('TOTAL Deduped SQL Found: {}'.format(len(logEntries['QUERIES'])))
        key = logStreamName + "_" + str(logEntries['METRICS']['FIRST_TS']) + "_" + str(logEntries['METRICS']['LAST_TS'])
        logger.info("Key: {}".format(key))
        g.logEntriesCache[key] = { 'logEntries': logEntries,
                                   'lastModifiedTime': time.time() * 1000,
                                   'oldestTimestamp': logEntries['METRICS']['FIRST_TS'],
                                   'newestTimestamp': logEntries['METRICS']['LAST_TS']
                                   }
    else:
        #  logEntries has no METRICS.. and therefore no entries
        #  update cache for startTime, endTime as this will
        #  be a "negative" cache
        g.logEntriesCache[key] = {'logEntries': logEntries,
                                  'lastModifiedTime': time.time() * 1000,
                                  'oldestTimestamp': startTime,
                                  'newestTimestamp': endTime
                                  }
    return ( g.logEntriesCache[key]['logEntries'])


def describeLogStreams(logGroupNameValue):
    client = boto3.client('logs')
    logStreams = {}
    response = client.describe_log_streams(logGroupName=logGroupNameValue)
    for elem in response['logStreams']:
        elem['logGroup'] = logGroupNameValue
        logStreams[elem['arn']] = elem
    while 'nextToken' in response:
        response = client.describe_log_streams(logGroupName=logGroupNameValue, nextToken=response['nextToken'])
        for elem in response['logStreams']:
            elem['logGroup'] = logGroupNameValue
            logStreams[elem['arn']] = elem
    logger.info('LogStreams Found: {}'.format(len(logStreams)))
    return logStreams



def describeLogGroups():
    client = boto3.client('logs')
    logGroups = []
    response = client.describe_log_groups(logGroupNamePrefix='/aws/rds/instance',limit=10)
    logGroups = response['logGroups']
    while 'nextToken' in response:
        response = client.describe_log_groups(logGroupNamePrefix='/aws/rds/instance', nextToken=response['nextToken'])
        logGroups = logGroups + response['logGroups']
    logger.info('LogGroups Found: {}'.format(len(logGroups)))
    return logGroups

import urllib
from markupsafe import Markup

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
        if (possible_ts > 1514764800000 ) and ( possible_ts < 2524608000000 ):
            s = "{} [ {} ]".format(
                datetime.datetime.fromtimestamp(possible_ts/1000.0),
                possible_ts
            )
    return Markup(s)

def startHttp():
    lockAcquired = False
    logger.info('Starting HTTP server...')
    if "DEBUG" in os.environ:
        app.run(debug=True, host='0.0.0.0', port=5150)
    else:
        app.run(host='0.0.0.0', port=5150)
    logger.info('HTTP Exiting...')
    sys.exit(0)

def startHttps():
    lockAcquired = False
    logger.info('Starting HTTPS server...')
    if "DEBUG" in os.environ:
        app.run(ssl_context='adhoc', debug=True, host='0.0.0.0', port=5151)
    else:
        app.run(ssl_context='adhoc', host='0.0.0.0', port=5151)
    logger.info('HTTPS Exiting...')
    sys.exit(0)

if __name__ == '__main__':
    # This starts the built in flask server, not designed for production use
    logger.setLevel(logging.INFO)
    logger.info('Setting up two processes for HTTP/HTTPS')
    p1 = Process(target=startHttp)
    p2 = Process(target=startHttps)
    p1.start()
    p2.start()
    p1.join()
    p2.join()
    logger.info('Exiting...')