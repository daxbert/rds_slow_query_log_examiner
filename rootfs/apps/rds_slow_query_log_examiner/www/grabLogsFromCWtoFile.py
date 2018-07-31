from __future__ import unicode_literals
import logging
import re
from pprint import  pprint
import os
import shelve

logger = logging.getLogger('rds_slow_query_log_examiner')
logger.propagate = False
stderr_logs = logging.StreamHandler()
stderr_logs.setLevel('DEBUG')
stderr_logs.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(stderr_logs)

logEntriesCache = {}

def setup():
    logger.info("Opening Cache")
    global logEntriesCache
    logEntriesCache = shelve.open("logEntriesCache.data",writeback=True)

def teardown():
    logger.info("Closing Cache")
    logEntriesCache.close()


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

def updateLogEntries(logEntries,le):
    if le['hash'] in logEntries:
       if ( len(logEntries[le['hash']]['queries']) < 4 ):
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
    if logStreamName in logEntriesCache:
        del logEntriesCache[logStreamName]

def clearCacheLogEntries(logGroup, logStreamName, startTime, endTime):
    if logStreamName in logEntriesCache:
        del logEntriesCache[logStreamName]

def getLogEntries(logGroup, logStreamName, startTime, endTime):
    return logEntriesCache[logStreamName]['logEntries']

def main():
    logger.info('Starting export...')
    setup()
    for stream in logEntriesCache:
        for key in logEntriesCache[stream]['logEntries']:
            for le in logEntriesCache[stream]['logEntries'][key]['queries']:
                print("{}".format(le['raw']))
    teardown()

if __name__ == '__main__':
    # This starts the built in flask server, not designed for production use
    logger.setLevel(logging.INFO)
    main()
    



