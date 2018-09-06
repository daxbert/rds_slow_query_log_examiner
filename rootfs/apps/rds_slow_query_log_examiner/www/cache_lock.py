from multiprocessing import Lock
import shelve

"""
This is a helper class to handle
locking the global cache object
"""


class CacheLock:
    def __init__(self, logger, g, session, web_protocol):
        self._cache_lock = Lock()
        self._g = g
        self._session = session
        self._web_protocol = web_protocol
        self.logger = logger

    def acquire_lock(self):
        self.logger.info("Acquiring Lock... {}".format(self._web_protocol))
        self._cache_lock.acquire()
        self.logger.info("Opening Cache")
        if 'AWS_ACCESS_KEY_ID' not in self._session:
            self.logger.info("Can't open cache files, no AWS key available")
            return 404

        log_entries_file = "logEntriesCache.{}.data".format(self._session['AWS_ACCESS_KEY_ID'])
        log_streams_file = "logStreamsCache.{}.data".format(self._session['AWS_ACCESS_KEY_ID'])

        self._g.logEntriesCache = shelve.open(log_entries_file, writeback=True)
        self._g.logStreamsCache = shelve.open(log_streams_file, writeback=True)
        self.logger.info("{}".format(self._g.logEntriesCache))
        self.logger.info("{}".format(self._g.logStreamsCache))
        self.logger.info("Acquired {}".format(self._web_protocol))

    def release_lock(self):
        self.logger.info("Release Lock...{}".format(self._web_protocol))
        self._g.logEntriesCache.close()
        self._g.logStreamsCache.close()
        self._cache_lock.release()
        self.logger.debug("Released {}".format(self._web_protocol))
