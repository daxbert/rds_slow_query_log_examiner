import re
from collections import OrderedDict

'''
This is a helper class to deal with
MySQL based SQL statements

TODO:  Add Postgres ( if needed )
'''
class SQL:

    def __init__(self, query):
        self._query = query
        self._fingerprint=None

    # This is an OrderedDict, because this must be processed in order
    # as listed
    fingerprintRegexs = OrderedDict(
        Values={
            'regex': [
                re.compile(r"VALUES\s*(.*)")
            ],
            'replace': "VALUES ( {VALUES_LIST} )"
        },
        # remove comments
        Comments={
            'regex': [
                re.compile(r"/\*.*?\*/")
            ],
            'replace': ''
        },
        # look for UUID like things, and replace with {UUID}
        UUIDs={
           'regex': [
                re.compile("[\"']*[0-9a-f]{32}['\"]*"),
                re.compile("[\"']*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[\"']*")
            ],
            'replace': "{UUID}"
        },
        # look for things that look like a SQL date, and replace with {DATE}
        Dates={
            'regex': [
                re.compile(r"'\d{4}-\d{2}-\d{2}'"),
                re.compile(r"'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}\.\d{1,}'"),
                re.compile(r"'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}'"),
                re.compile(r"'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{2}:\d{2}'"),
                re.compile(r"'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'"),
            ],
            'replace': "{DATE}"
        },
        # Hibernate builds queries with #'d field names
        # remove the specific #s, and make more generic
        Hibernate={
            'regex': [
                re.compile(r"\d+_")
            ],
            'replace': '#_'
        },
        # look for consecutive digits >= 4 and replace with ####
        Numbers={
            'regex': [
                re.compile(r"\d{4,}"),
                re.compile(r"[-\.\d]{4,}"),
                re.compile(r"####\s*,\s*####\s*,\s*####,[\s,#]*,\s*####")
            ],
            'replace': '####'
        },
        String={
            'regex': [
                re.compile(r"'.*?'")
            ],
            'replace': "'{STRING}'"
        }
    )

    def fingerprint(self):
        if ( self._fingerprint ):
            return self._fingerprint

        filteredSql = ""

        for line in self._query.splitlines():

            # Perform all of the regex replacements
            for regexName in self.fingerprintRegexs:
                for regex in self.fingerprintRegexs[regexName]['regex']:
                    line = regex.sub(self.fingerprintRegexs[regexName]['replace'], line)

            filteredSql = filteredSql + line + "\n"

        _fingerprint = filteredSql
        return _fingerprint

