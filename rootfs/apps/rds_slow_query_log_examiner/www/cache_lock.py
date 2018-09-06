from flask import g, session
from multiprocessing import Lock
import shelve

"""
This is a helper class to handle
locking the global cache object
"""


class CacheLock:
    def __init__(self):
        self._cache_lock = Lock()

    def acquire_lock(self):
        g.logger.info("Acquiring Lock... {}".format(g.web_protocol))
        self._cache_lock.acquire()
        g.logger.info("Opening Cache")
        if 'AWS_ACCESS_KEY_ID' not in session:
            g.logger.info("Can't open cache files, no AWS key available")
            return 404

        log_entries_file = "logEntriesCache.{}.data".format(session['AWS_ACCESS_KEY_ID'])
        log_streams_file = "logStreamsCache.{}.data".format(session['AWS_ACCESS_KEY_ID'])

        g.logEntriesCache = shelve.open(log_entries_file, writeback=True)
        g.logStreamsCache = shelve.open(log_streams_file, writeback=True)
        g.logger.info("{}".format(g.logEntriesCache))
        g.logger.info("{}".format(g.logStreamsCache))
        g.logger.info("Acquired {}".format(g.web_protocol))

    def release_lock(self):
        g.logger.info("Release Lock...{}".format(g.web_protocol))
        g.logEntriesCache.close()
        g.logStreamsCache.close()
        self._cache_lock.release()
        g.logger.debug("Released {}".format(g.web_protocol))
