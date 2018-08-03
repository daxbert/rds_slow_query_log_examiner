from __future__ import unicode_literals
from flask import Flask, request, redirect, jsonify, abort, render_template,  g
# from werkzeug.exceptions import NotFound
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

MAX_QUERIES=20000

app = Flask(__name__)
logger = logging.getLogger('rds_slow_query_log_examiner')
logger.setLevel('DEBUG')
logger.propagate = False
stderr_logs = logging.StreamHandler()
stderr_logs.setLevel('DEBUG')
stderr_logs.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(stderr_logs)

@app.before_request
def before_req():
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

regexUUIDs = [ 
    re.compile(r"[0-9a-f]{32}"),
    re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
]

regexDates = [ 
    re.compile(r"'\d{4}-\d{2}-\d{2}'"),
    re.compile(r"'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}\.\d{1,}'"),
    re.compile(r"'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}'"),
    re.compile(r"'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{2}:\d{2}'"),
    re.compile(r"'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'"),
]

regexComments = [
    re.compile(r"/\*.*?\*/")
]

regexString = [
    re.compile(r"'.*?'")
]

regexHibernate = [
    re.compile(r"\d+_")
]

regexValues = [
    re.compile(r"VALUES\s*(.*)")
]

regexNumbers = [
    re.compile(r"\d{4,}"),
    re.compile(r"[-\.\d]{4,}"),
    re.compile(r"####\s*,\s*####\s*,\s*####,[\s,#]*,\s*####")
]
# re.compile(r"d{4,}"),
    
def filterNumbers(sql):
    filteredSql = ""
    for line in sql.splitlines():

        # Replace Values expression with {VALUES_LIST}
        for regex in regexValues:
             line = regex.sub("VALUES ( {VALUES_LIST} )",line)

        # remove comments
        for regex in regexComments:
            line = regex.sub("",line)

        # look for UUID like things, and replace with {UUID}
        for regex in regexUUIDs:
            line = regex.sub("{UUID}",line)

        for regex in regexDates:
            line = regex.sub("'{DATE}'",line)

        # look for hibernate names
        for regex in regexHibernate:
            line = regex.sub("#_",line)

        # look for consecutive digits >= 4 and replace with ####
        for regex in regexNumbers:
            line = regex.sub("####",line)

        for regex in regexString:
            line = regex.sub("'{STRING}'",line)

        filteredSql = filteredSql + line + "\n"
    return filteredSql

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
        return None
    else:
        return { 'qtime': qtime, 'session': session, 'rows': rows, 'sent': sent, 'ltime': ltime, 'query': query, 'raw': cw_event['message'], 'timestamp': cw_event['timestamp'] }

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
    if "startDateString" in request.args:
        startDateString = request.args["startDateString"]
        startDateTimestamp = int(datetime.datetime.strptime(startDateString, "%Y/%m/%d %H:%M:%S").timestamp() * 1000)
    else:
        logger.info("startDateString NOT IN URL")
        logger.info("{}".format(pprint.pformat(request.args)))

    if "endDateString" in request.args:
        endDateString = request.args["endDateString"]
        endDateTimestamp = int(datetime.datetime.strptime(endDateString, "%Y/%m/%d %H:%M:%S").timestamp() * 1000)
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
            if ( startDateTimestamp ):
                logger.info("startDateTimestamp specified: {}".format(startDateTimestamp))
                if ( startDateTimestamp < stream['firstEventTimestamp'] ):
                    start_timestamp = stream['firstEventTimestamp']
                else:
                    start_timestamp = startDateTimestamp
                logger.info("start_timestamp: {}".format(start_timestamp))
            if ( endDateTimestamp ):
                logger.info("endDateTimestamp specified: {}".format(endDateTimestamp))
                if ( endDateTimestamp > stream['lastEventTimestamp'] ):
                    end_timestamp = stream['lastEventTimestamp']
                else:
                    end_timestamp = endDateTimestamp
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
                ( logEntries, oldestTimestamp, newestTimestamp ) = getLogEntries(stream['logGroup'], stream['logStreamName'], start_timestamp, end_timestamp)
            logger.info("oldestTimestamp: {} {}".format(oldestTimestamp, datetime.datetime.fromtimestamp(oldestTimestamp/1000.0))) 
            logger.info("newestTimestamp: {} {}".format(newestTimestamp, datetime.datetime.fromtimestamp(newestTimestamp/1000.0)))
            return render_template('stream_data.html', stream = stream, ui = ui, logEntries = logEntries, os = os, start_timestamp = oldestTimestamp, end_timestamp = newestTimestamp )

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
    logGroups = describeLogGroups()
    allLogStreams = {}
    for logGroup in logGroups:
        if "slowquery" not in logGroup['logGroupName']:
            continue
        logger.info('Group: {}'.format(logGroup['logGroupName']))
        logStreams = describeLogStreams(logGroup['logGroupName'])
        allLogStreams.update(logStreams)
        logger.debug('Streams: {}'.format(logStreams))
    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']] = {}
    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['lastModifiedTime'] = time.time() * 1000
    g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['logStreams'] = allLogStreams
    return g.logStreamsCache[os.environ['AWS_DEFAULT_REGION']]['logStreams']

def updateLogEntries(logEntries,le):
    if le['hash'] in logEntries:
       if ( len(logEntries[le['hash']]['queries']) < MAX_QUERIES ):
           logEntries[le['hash']]['queries'].append(le)
           logger.debug("LEN: {}".format(len(logEntries[le['hash']]['queries'])))
       logEntries[le['hash']]['totalcount'] = logEntries[le['hash']]['totalcount'] + 1 
       logEntries[le['hash']]['totalrows'] = logEntries[le['hash']]['totalrows'] + int(le['rows'])
       logEntries[le['hash']]['totalsent'] = logEntries[le['hash']]['totalsent'] + int(le['sent'])
       logEntries[le['hash']]['totalqtime'] = logEntries[le['hash']]['totalqtime'] + float(le['qtime']) 
       logEntries[le['hash']]['totalltime'] = logEntries[le['hash']]['totalltime'] + float(le['ltime']) 
    else:
       logEntries[le['hash']] = { 
                                   'queries': [ le ],
                                   'totalcount' : 1,
                                   'totalsent' : int(le['sent']), 
                                   'totalrows' : int(le['rows']), 
                                   'totalqtime' : float(le['qtime']),
                                   'totalltime' : float(le['ltime']) 
                                }
    return logEntries

def clearCacheStreamEntries(logGroup, logStreamName, startTime, endTime):
    if logStreamName in g.logEntriesCache:
        del g.logEntriesCache[logStreamName]

def clearCacheLogEntries(logGroup, logStreamName, startTime, endTime):
    if logStreamName in g.logEntriesCache:
        del g.logEntriesCache[logStreamName]

def getLogEntries(logGroup, logStreamName, startTime, endTime):
    key = logStreamName + "_" + str(startTime) + "_" + str(endTime)
    logger.info("Key: {}".format(key))
    if key in g.logEntriesCache:
        if g.logEntriesCache[key]['lastModifiedTime'] > oldestViableCacheTimestamp():
            return ( g.logEntriesCache[key]['logEntries'], g.logEntriesCache[key]['oldestTimestamp'], g.logEntriesCache[key]['newestTimestamp'] )
    client = boto3.client('logs')
    logEntries = {}
    budgetLeft = MAX_QUERIES
    response = client.get_log_events(logGroupName = logGroup,logStreamName = logStreamName,startTime = startTime, endTime = endTime,startFromHead=False)
    logger.info("LE1: {}".format(len(response['events'])))
    budgetLeft = budgetLeft - len(response['events'])
    logger.info("Budget Left: {}".format(budgetLeft))
    oldestTimestamp = endTime;
    newestTimestamp = endTime;
    if ( len(response['events']) > 0 ):
        ts = response['events'][0]['timestamp']
        if ( ts > newestTimestamp ):
            newestTimestamp = ts
        if ( ts < oldestTimestamp ):
            oldestTimestamp = ts
        logger.info("TS: {} is {}".format(ts,datetime.datetime.fromtimestamp(ts/1000.0)))
        ts = response['events'][len(response['events']) - 1]['timestamp']
        if ( ts > newestTimestamp ):
            newestTimestamp = ts
        if ( ts < oldestTimestamp ):
            oldestTimestamp = ts
        logger.info("TS: {} is {}".format(ts,datetime.datetime.fromtimestamp(ts/1000.0)))
        for event in response['events']:
           le = parseLogEntry(event)
           if le is None:
               return None
           le['hash'] = filterNumbers(le['query'])
           logEntries = updateLogEntries(logEntries, le)
    while (budgetLeft > 0 and len(response['events']) > 0):
        response = client.get_log_events(logGroupName = logGroup,logStreamName = logStreamName, startTime = startTime, endTime = endTime, startFromHead=False, nextToken=response['nextBackwardToken'])
        logger.info("LE2: {}".format(len(response['events'])))
        budgetLeft = budgetLeft - len(response['events'])
        logger.info("Budget Left: {}".format(budgetLeft))
        if ( len(response['events']) > 0 ):
            ts = response['events'][0]['timestamp']
            if ( ts > newestTimestamp ):
                 newestTimestamp = ts
            if ( ts < oldestTimestamp ):
                oldestTimestamp = ts
            logger.info("TS: {} is {}".format(ts,datetime.datetime.fromtimestamp(ts/1000.0)))
            ts = response['events'][len(response['events']) - 1]['timestamp']
            if ( ts > newestTimestamp ):
                newestTimestamp = ts
            if ( ts < oldestTimestamp ):
                oldestTimestamp = ts
            logger.info("TS: {} is {}".format(ts,datetime.datetime.fromtimestamp(ts/1000.0)))
            for event in response['events']:
                le = parseLogEntry(event)
                if le is None:
                    return None
                le['hash'] = filterNumbers(le['query'])
                logEntries = updateLogEntries(logEntries, le)
    logger.info('TOTAL Deduped SQL Found: {}'.format(len(logEntries)))
    key = logStreamName + "_" + str(oldestTimestamp) + "_" + str(newestTimestamp)
    logger.info("Key: {}".format(key))
    g.logEntriesCache[key] = { 'logEntries': logEntries, 'lastModifiedTime': time.time() * 1000, 'oldestTimestamp': oldestTimestamp, 'newestTimestamp': newestTimestamp }
    return ( g.logEntriesCache[key]['logEntries'], g.logEntriesCache[key]['oldestTimestamp'], g.logEntriesCache[key]['newestTimestamp'] )


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
#aws logs describe-log-groups --log-group-name-prefix /aws/rds/instance/ |  jq '.[] | .[] | select(.logGroupName | contains("slowquery"))'
if __name__ == '__main__':
    # This starts the built in flask server, not designed for production use
    logger.setLevel(logging.INFO)
    logger.info('Starting server...')
    if "DEBUG" in os.environ:
        app.run(debug=True, host='0.0.0.0', port=5150)
    else:
        app.run(host='0.0.0.0', port=5150)



