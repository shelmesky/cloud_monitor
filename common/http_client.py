import httplib2
import urllib
import logging
import copy
import json
import sys

class Client(object):
    def __init__(self,api):
        self.api = api
    
    def listinstance(self):
        url = '/api/instance/uuid'
        content = {}
        resp,body = self.api.get(url, body=content)
        return body
 

class _HTTPClient(httplib2.Http):
    def __init__(self, username=None, password=None, api_url=None,
                 token=None, timeout=None):
        super(_HTTPClient, self).__init__(timeout=timeout)
        self.username = username
        self.password = password
        self.api_url  = api_url
        self.token = token

    def request(self, url, method, **kwargs):
        request_kwargs = copy.copy(kwargs)
        request_kwargs.setdefault('headers', kwargs.get('headers', {}))
        request_kwargs['headers']['Accept'] = 'application/json'
        try:
            request_kwargs['body']['token'] = self.token
            request_kwargs['body'] = urllib.urlencode(kwargs['body'])
        except KeyError:
            pass
        resp, body = super(_HTTPClient, self).request(self.api_url + url,
                                                      method, **request_kwargs)
        
        return resp,body


class _api_client(_HTTPClient):
    def __init__(self, **kwargs):
        super(_api_client,self).__init__(**kwargs)
        self.interface = Client(self)
    
    def post(self, url, **kwargs):
        return self.request(url, 'POST', **kwargs)
    
    def get(self, url, **kwargs):
        return self.request(url, 'GET', **kwargs)
