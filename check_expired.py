#!/usr/bin/python
# coding: utf-8
import datetime
import dateutil
import logging
import traceback
import sys

from cloud_monitor_settings import *

try:
    import web as _web
except (ImportError,ImportWarning) as e:
    print "Can not find python-webpy, in ubuntu just run \"sudo apt-get install python-webpy\"."
    print e
    sys.exit(1)

logfile = 'check_expired.py.log'


_web.config.debug = True

_db = _web.database(dbn=db_engine,host=db_server,db=db_database,user=db_username,pw=db_password)

def trace():
    info = sys.exc_info()
    for filename, lineno, function, text in traceback.extract_tb(info[2]):
        info1 = (str(filename) + " line " + str(lineno) + " in " + str(function))
        info2 = "=> " + str(text)
    info3 = "** %s: %s" % info[:2]
    return "%s \n %s \n %s" % (info1,info2,info3)

def initlog(logfile):
    logger = logging.getLogger()
    handler = logging.FileHandler(logfile)
    formatter = logging.Formatter("%(levelname)s [%(asctime)s]: %(message)s\n","%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.NOTSET)
    return logger

def _check_expired_cloud_host():
    table = 'cloud_host'
    logger = initlog(logfile)
    try:
        lines = _db.select(table,what='uuid,expired_time').list()
        now_date = datetime.date.today().strftime("%Y%m%d")
        for line in lines:
            expired_time = line['expired_time']
            uuid = line['uuid']
            if expired_time and int(expired_time) < int(now_date):
                _db.update(table,where="`uuid`='%s'" % uuid,enable=0,expired_time = '')
    except:
        err = trace()
        logger.error(err)


def _check_expired_cloud_token():
    table = 'cloud_apiserver_tokens'
    logger = initlog(logfile)
    try:
        lines = _db.select(table,what='token,last_use_time').list()
        now_date = datetime.date.today().strftime("%Y%m%d%H%M")
        for line in lines:
            token = line['token']
            last_use_time = line['last_use_time']
            if last_use_time: no_active_time = int(now_date) - int(last_use_time)
            if no_active_time >= 720:
                _db.delete(table,where="`token`='%s'" % token)
    except:
        err = trace()
        logger.error(err)

if __name__ == '__main__':
    _check_expired_cloud_host()
    _check_expired_cloud_token()
