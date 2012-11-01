import os, sys
import simplejson
from http_client import _api_client as http_client

sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             os.path.pardir))

import cloud_monitor_settings

api_url = cloud_monitor_settings.loadbalance_server


def _httpclient():
    c = http_client(api_url=api_url)
    return c

def listinstance():
    ret = _httpclient().interface.listinstance()
    return simplejson.loads(ret)


if __name__ == '__main__':
    print "test listinstance()"
    print listinstance()
