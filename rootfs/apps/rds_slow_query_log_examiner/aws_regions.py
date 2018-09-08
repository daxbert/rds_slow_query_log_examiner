"""
This is a helper class for
AWS' regions
"""


class AWSRegions:
    def __init__(self, client):
        self._client = client
        self._regions = {}

    def get(self):
        if self._regions:
            return self._regions

        self._regions = self._client.api("list", "describe_regions", {}, lambda x: x['Regions'])

        return self._regions
