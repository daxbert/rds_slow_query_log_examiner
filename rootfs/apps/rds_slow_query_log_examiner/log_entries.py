from flask import g
import datetime
import time
import json
from rds_slow_query_log_examiner.cw_event import CWEvent
from rds_slow_query_log_examiner.sql import SqlQuery

'''
This is a helper class to aggregate
CloudWatch slow query log events

'''

MAX_QUERIES_TO_PARSE = 20000
MAX_QUERIES_TO_APPEND = 10


class LogEntries:

    def __init__(self, log_stream_name):
        self._log_entries = {'QUERIES': {}, 'METRICS': {}}
        self._count = 0
        self._log_stream_name = log_stream_name
        self._max_queries_to_append = MAX_QUERIES_TO_APPEND

    def set_max_queries_to_append(self, max_append):
        self._max_queries_to_append = max_append

    @staticmethod
    def oldest_viable_cache_timestamp():
        # 1 Hour ago...
        return (time.time() * 1000) - (60 * 60 * 1000)

    def _add_entry(self, new_entry):
        self._count += 1
        if new_entry['hash'] in self._log_entries['QUERIES']:
            existing_entry = self._log_entries['QUERIES'][new_entry['hash']]
            if len(existing_entry['queries']) < MAX_QUERIES_TO_APPEND:
                existing_entry['queries'].append(new_entry)
                g.logger.debug("LEN: {}".format(len(existing_entry['queries'])))
            existing_entry['totalcount'] += 1
            existing_entry['totalrows'] += int(new_entry['rows'])
            existing_entry['totalsent'] += int(new_entry['sent'])
            existing_entry['totalqtime'] += float(new_entry['qtime'])
            existing_entry['totalltime'] += float(new_entry['ltime'])
            for metric in ("sent", "rows", "qtime", "ltime"):
                if new_entry[metric] > existing_entry['slowest'][metric][metric]:
                    existing_entry['slowest'][metric] = new_entry
        else:
            self._log_entries['QUERIES'][new_entry['hash']] = {
                'queries': [new_entry],
                'slowest': {
                    'sent': new_entry,
                    'rows': new_entry,
                    'qtime': new_entry,
                    'ltime': new_entry
                    },
                'totalcount': 1,
                'hash': new_entry['hash'],
                'totalsent': int(new_entry['sent']),
                'totalrows': int(new_entry['rows']),
                'totalqtime': float(new_entry['qtime']),
                'totalltime': float(new_entry['ltime'])
            }

        if 'TOTAL_QUERY_COUNT' in self._log_entries['METRICS']:
            self._log_entries['METRICS']['TOTAL_QUERY_COUNT'] += 1
            self._log_entries['METRICS']['TOTAL_ROWS'] += int(new_entry['rows'])
            self._log_entries['METRICS']['TOTAL_SENT'] += int(new_entry['sent'])
            self._log_entries['METRICS']['TOTAL_QTIME'] += float(new_entry['qtime'])
            self._log_entries['METRICS']['TOTAL_LTIME'] += float(new_entry['ltime'])
            ts = new_entry['event']['timestamp']
            if ts < self._log_entries['METRICS']['FIRST_TS']:
                self._log_entries['METRICS']['FIRST_TS'] = ts
            if ts > self._log_entries['METRICS']['LAST_TS']:
                self._log_entries['METRICS']['LAST_TS'] = ts
        else:
            self._log_entries['METRICS']['TOTAL_QUERY_COUNT'] = 1
            self._log_entries['METRICS']['FIRST_TS'] = new_entry['event']['timestamp']
            self._log_entries['METRICS']['LAST_TS'] = new_entry['event']['timestamp']
            self._log_entries['METRICS']['TOTAL_ROWS'] = int(new_entry['rows'])
            self._log_entries['METRICS']['TOTAL_SENT'] = int(new_entry['sent'])
            self._log_entries['METRICS']['TOTAL_QTIME'] = float(new_entry['qtime'])
            self._log_entries['METRICS']['TOTAL_LTIME'] = float(new_entry['ltime'])

    def report_metrics(self, logger):
        logger.info('TOTAL Queries Parsed: {}'.format(self._log_entries['METRICS']['TOTAL_QUERY_COUNT']))
        logger.info('TOTAL Deduped SQL Found: {}'.format(len(self._log_entries['QUERIES'])))

    def update_cache(self, cache):
        key = self._log_stream_name + \
              "_" + \
              str(self._log_entries['METRICS']['FIRST_TS']) + \
              "_" + \
              str(self._log_entries['METRICS']['LAST_TS'])
        g.logger.info("Key: {}".format(key))
        cache[key] = {
            'logEntries': self._log_entries,
            'lastModifiedTime': time.time() * 1000,
            'oldestTimestamp': self._log_entries['METRICS']['FIRST_TS'],
            'newestTimestamp': self._log_entries['METRICS']['LAST_TS'],
        }

    def get_count(self):
        return self._count

    def get_queries(self):
        return self._log_entries['QUERIES']

    def get_metrics(self):
        return self._log_entries['METRICS']

    def get_oldest_ts(self):
        return self._log_entries['METRICS']['FIRST_TS']

    def get_newest_ts(self):
        return self._log_entries['METRICS']['LAST_TS']

    def process_response(self, response):
        g.logger.info("Event Count: {}".format(len(response['events'])))
        if len(response['events']) > 0:
            first_ts = response['events'][0]['timestamp']
            last_ts = response['events'][len(response['events']) - 1]['timestamp']
            if last_ts < first_ts:
                first_ts, last_ts = last_ts, first_ts
            g.logger.info("Stream: {} from {} to {}".format(
                self._log_stream_name,
                datetime.datetime.fromtimestamp(first_ts/1000.0),
                datetime.datetime.fromtimestamp(last_ts / 1000.0)))
            for event in response['events']:
                le = (CWEvent(event)).parse()
                if le is None:
                    return 0
                le['hash'] = (SqlQuery(le['query'])).fingerprint()
                self._add_entry(le)
        return len(response['events'])

    def get_queries_as_json(self):
        output = ""
        for key, entry in (self.get_queries()).items():
            output += json.dumps(entry) + ",\n\n\n"
        return output

    @staticmethod
    def get_log_entries(log_group, log_stream_name, start_time, end_time, lock):
        key = log_stream_name + "_" + str(start_time) + "_" + str(end_time)
        g.logger.info("Key: {}".format(key))

        lock.acquire_lock()
        if key in g.logEntriesCache:
            if g.logEntriesCache[key]['lastModifiedTime'] > LogEntries.oldest_viable_cache_timestamp():
                temp_array = (
                    g.logEntriesCache[key]['logEntries'],
                    g.logEntriesCache[key]['oldestTimestamp'],
                    g.logEntriesCache[key]['newestTimestamp']
                )
                lock.release_lock()
                return temp_array
        lock.release_lock()

        log_entries = LogEntries(log_stream_name)
        budget_left = MAX_QUERIES_TO_PARSE
        client = g.aws_clients.get_client("logs", g.aws_region)

        response = client.api(
            "dict",
            "get_log_events",
            {
                'logGroupName': log_group,
                'logStreamName': log_stream_name,
                'startTime': start_time,
                'endTime': end_time,
                'startFromHead': False
            },
            lambda x: x
        )

        count = log_entries.process_response(response)
        budget_left = budget_left - count
        g.logger.info("Budget Left: {}".format(budget_left))

        while budget_left > 0 and count > 0:
            response = client.api(
                "dict",
                "get_log_events",
                {
                    'logGroupName': log_group,
                    'logStreamName': log_stream_name,
                    'startTime': start_time,
                    'endTime': end_time,
                    'startFromHead': False,
                    'nextToken': response['nextBackwardToken']
                },
                lambda x: x
            )
            count = log_entries.process_response(response)
            budget_left = budget_left - count
            g.logger.info("Budget Left: {}".format(budget_left))

        if log_entries.get_count() > 0:
            log_entries.report_metrics(g.logger)

            lock.acquire_lock()
            log_entries.update_cache(g.logEntriesCache)
            lock.release_lock()

        return log_entries
