from flask import session
import boto3

"""
This is a helper class for AWS client
management.  It creates clients and stores them 
as an instance dict
"""


class AWSClientFactory:

    def __init__(self):
        self._clients = {}

    def get_client(self, mode, region):
        key = mode + "_client"
        if key not in self._clients:
            self._clients[key] = {}
        if region not in self._clients[key]:
            self._clients[key][region] = AWSClient(mode, region)
        return self._clients[key][region]


class AWSClient:

    def __init__(self, mode, region):
        self._client = boto3.client(
            mode,
            aws_access_key_id=session['AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=session['AWS_SECRET_ACCESS_KEY'],
            region_name=region
        )

    def api(self, return_type, method, args, response_function):
        actual_method = getattr(self._client, method)
        response = actual_method(**args)
        r = response_function(response)
        while 'nextToken' in response:
            args['nextToken'] = response['nextToken']
            response = actual_method(**args)
            t = response_function(response)
            if return_type == "dict":
                r = {**r, **t}
            else:
                r = r + t
        return r
