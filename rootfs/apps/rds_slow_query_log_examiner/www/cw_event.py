from flask import g
import re

'''
This is a helper class to parse
CloudWatch slow query log events
'''

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


class CWEvent:
    """
    static regex patterns used in the parse_log_entry function
    """

    def __init__(self, event):
        self._event = event

    @staticmethod
    def skip_line(line):
        for regex in regexLinesToIgnore:
            if bool(regex.match(line)):
                g.logger.debug("IGNORE: {}".format(line))
                return True
        return False

    def parse(self):
        cw_event = self._event
        query = None
        query_time = None
        lock_time = None
        sent = None
        rows = None
        host = None
        user = None
        log_session = None
        for line in cw_event['message'].splitlines():
            g.logger.debug("LINE: {}".format(line))
            user_info = regexUserInfo.match(line)
            if user_info:
                query = ""
                user = user_info.group(1)
                host = user_info.group(2)
                log_session = user_info.group(3)
                continue

            if bool(re.match('^# Query_time:', line)):
                query = ""
                g.logger.debug("QT LIKELY: {}".format(line))
                m = regexPerformance.match(line)
                if m:
                    query_time = float(m.group(1))
                    lock_time = float(m.group(2))
                    sent = int(m.group(3))
                    rows = int(m.group(4))
                    g.logger.debug("QT OK: {} {}".format(query_time, rows))
                else:
                    g.logger.debug("QT ERROR: {}".format(line))
                continue

            if self.skip_line(line):
                continue

            query = query + line + "\t"

        # done with the entry... do we have a pending query to output
        if any(x is None for x in [rows, query_time, lock_time, user, host]):
            g.logger.info("PARSE_FAILED: {}".format(cw_event))
            g.logger.info("PARSE_FAILED: {} {} {} {} {}".format(
                rows,
                query_time,
                lock_time,
                user,
                host
            ))
        return {
            'event': cw_event,
            'qtime': query_time,
            'session': log_session,
            'rows': rows,
            'sent': sent,
            'ltime': lock_time,
            'query': query,
            'raw': cw_event['message'],
            'timestamp': cw_event['timestamp']
        }
