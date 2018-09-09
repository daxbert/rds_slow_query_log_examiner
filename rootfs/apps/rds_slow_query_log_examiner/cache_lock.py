from flask import g, session
from multiprocessing import Lock
import shelve
import os

"""
This is a helper class to handle
locking the global cache object
"""


class CacheLock:
    def __init__(self):
        self._cache_lock = Lock()
        self._log_entries_file = None
        self._log_streams_file = None

    def acquire_lock(self):
        g.logger.info("Acquiring Lock... {}".format(g.web_protocol))
        self._cache_lock.acquire()
        g.logger.info("Opening Cache")
        if 'AWS_ACCESS_KEY_ID' not in session:
            g.logger.info("Can't open cache files, no AWS key available")
            return 404

        if not self._log_entries_file:
            self._log_entries_file = "logEntriesCache.{}.data".format(session['AWS_ACCESS_KEY_ID'])
        if not self._log_streams_file:
            self._log_streams_file = "logStreamsCache.{}.data".format(session['AWS_ACCESS_KEY_ID'])

        g.logEntriesCache = shelve.open(self._log_entries_file, writeback=True)
        g.logStreamsCache = shelve.open(self._log_streams_file, writeback=True)
        g.logger.debug("{}".format(g.logEntriesCache))
        g.logger.debug("{}".format(g.logStreamsCache))
        g.logger.info("Acquired {}".format(g.web_protocol))

    def release_lock(self):
        g.logger.info("Release Lock...{}".format(g.web_protocol))
        if 'logEntriesCache' in g:
            g.logEntriesCache.close()
        if 'logStreamsCache'in g:
            g.logStreamsCache.close()
        self._cache_lock.release()
        g.logger.debug("Released {}".format(g.web_protocol))

    def delete_caches(self):
        self.acquire_lock()

        if 'logEntriesCache'in g:
            g.logEntriesCache.close()
            del g['logEntriesCache']
        if self._log_entries_file:
            os.remove(self._log_entries_file)
            self._log_entries_file = None

        if 'logStreamsCache' in g:
            g.logStremsCache.close()
            del g['logStreamsCache']
        if self._log_streams_file:
            os.remove(self._log_streams_file)
            self._log_streams_file = None

        self.release_lock()
