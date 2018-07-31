#!/bin/sh

mkdir report_$$
python36 grabLogsFromCWtoFile.py > report_$$/log.txt
pt-query-digest --limit 100% --progress percentage,5 --max-line-length 180 report_$$/log.txt > report_$$/report.txt
pt-query-digest --limit 100% --progress percentage,5 --max-line-length 180 --output json report_$$/log.txt > report_$$/report.json
cp logEntriesCache.data report_$$/logEntriesCache.data
