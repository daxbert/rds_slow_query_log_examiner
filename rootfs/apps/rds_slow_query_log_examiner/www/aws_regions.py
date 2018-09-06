"""
This is a helper class for
AWS' regions
"""


class AWSRegions:
    def __init__(self, client, logger):
        self._client = client
        self.logger = logger
        self._regions = {}

    def get(self):
        if self._regions:
            return self._regions

        response = self._client.describe_regions()
        self._regions = response['Regions']

        return self._regions


