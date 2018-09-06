from flask import session
import boto3

"""
This is a helper class for AWS client
management.  It creates clients and stores them 
as an instance dict
"""


class AWSClient:

    def __init__(self):
        self._clients = {}

    def get_client(self, mode, region):
        key = mode + "_client"
        if key not in self._clients:
            self._clients[key] = {}
            if region not in self._clients[key]:
                self._clients[key][region] = boto3.client(
                    mode,
                    aws_access_key_id=session['AWS_ACCESS_KEY_ID'],
                    aws_secret_access_key=session['AWS_SECRET_ACCESS_KEY'],
                    region_name=region
                )
        return self._clients[key][region]
