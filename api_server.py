#!/usr/bin/python

try:
    from gevent import monkey
    monkey.patch_all()
    from gevent.wsgi import WSGIServer
    import gevent
except (ImportError,ImportWarning) as e:
    print "Can not find python-gevent, in ubuntu just run \"sudo apt-get install python-gevent\"."
    print e
    sys.exit(1)

import os
import sys
import json
import time
from mimerender import mimerender
from multiprocessing import Process
import uuid

try:
    import web as _web
    from web import session as _session
except (ImportError,ImportWarning) as e:
    print "Can not find python-webpy, in ubuntu just run \"sudo apt-get install python-webpy\"."
    print e
    sys.exit(1)

    
_web.config.debug = True

db = _web.database(dbn='mysql',db='cloud_monitor',user='root',pw='root')

render_xml = lambda message: '<message>%s</message>' % message
render_json = lambda **args: json.dumps(args)
render_html = lambda message: '<html><body>%s</body></html>' % message
render_txt = lambda message: message

urls = (
    '/login','login',
    '/logout','logout',
    '/setinterval','setInterval',
    '/enablebyuuid','enableByUUID',
    '/getdatabyuuid','getDataByUUID',
    '/getminutesbyuuid','getMinutesByUUID',
    '/gethoursbyuuid','getHoursByUUID',
    '/getdaysbyuuid','getDaysByUUID',
    '/getmonthsbyuuid','getMonthByUUID',
    '/getyearbyuuid','getYearByUUID',
    '/gateway','gateway',
    '/benchmark','Benchmark',
    '/getinstancelist','getInstanceList',
)

class tokens(object):
    tokens_table = "cloud_apiserver_tokens"
    @staticmethod
    def get_all_tokens():
        return db.select(tokens.tokens_table).list()
    
    @staticmethod
    def insert_token(token):
        if not db.select(tokens.tokens_table,where="`token`='%s'" % token).list():
            db.insert(tokens.tokens_table,token=token)
            return True
        return False
    
    @staticmethod
    def update_token(token):
        timedate = time.strftime('%Y%m%d%H%M',time.localtime())
        last_use_time = db.select(tokens.tokens_table,where="`token`='%s'" % token).list()[0]['last_use_time']
        if not last_use_time:
            last_use_time = 0
        else:
            last_use_time = int(last_use_time)
        no_active_time = int(timedate) - last_use_time
        if last_use_time and no_active_time >= 720:
            db.delete(tokens.tokens_table,where="`token`='%s'" % token)
            return False
        db.update(tokens.tokens_table,where="`token`='%s'" % token,last_use_time=timedate)
        return True
    
    @staticmethod
    def remove_token(token):
        if db.delete(tokens.tokens_table,where="`token`='%s'" % token) != 1:
            raise ValueError,"no record"


def require_login(func):
    def proxy(self,*args,**kw):
        try:
            token =  _web.input()['token']
        except KeyError:
            return {'message':'not_login'}
        else:
            for line in tokens.get_all_tokens():
                if token == line['token']:
                    if not tokens.update_token(token):
                        return {'message':'token_timeout'}
                    return func(self,*args,**kw)
            return {'message':'incorrect_token'} 
    return proxy

class login(object):
    @mimerender(
        default = 'json',
        html = render_html,
        xml  = render_xml,
        json = render_json,
        txt  = render_txt
    )
    def POST(self):
        data = _web.input()
        try:
            username = getattr(data,'username')
            password = getattr(data,'password')
        except AttributeError:
            return {'message':'need_auth_info'}
        else:
            if db.select('cloud_apiserver_user',where="`username`='%s' and `password`='%s'" % (username,password)).list():
                token = str(uuid.uuid4())
                if not tokens.insert_token(token):
                    return {'message':'allready_login!'}
            else:
                return {'message':'wrong_username_or_password'}
        return {'message':{'token':token}}

class logout(object):
    @mimerender(
        default = 'json',
        html = render_html,
        xml  = render_xml,
        json = render_json,
        txt  = render_txt
    )
    def POST(self):
        data = _web.input()
        try:
            token = getattr(data,'token')
        except AttributeError:
            return {'message':'need_token_info'}
        else:
            try:
                tokens.remove_token(token)
            except ValueError:
                return {'message':'logout_error'}
            else:
                return {'message':'logout_success'}

class getInstanceList(object):
    @mimerender(
        default = 'json',
        html = render_html,
        xml  = render_xml,
        json = render_json,
        txt  = render_txt
    )
    @require_login
    def POST(self):
        table = 'cloud_host'
        results = list()
        ret = db.select(table,what='id,enable,uuid')
        for line in ret:
            results.append(line)
        return {'message':results}

class setInterval():
    @mimerender(
        default = 'json',
        html = render_html,
        xml  = render_xml,
        json = render_json,
        txt  = render_txt
    )
    @require_login
    def POST(self):
        table='cloud_config'
        data = _web.input()
        try:
            interval = data.interval
        except AttributeError:
            return {'message':'failed'}
        if not int(interval)>0 or not int(interval)<3600: return {'message':'failed'}
        db.update(table,where="`key`='interval'",value=interval)
        return {'message':'success'}


class enableByUUID():
    @mimerender(
        default='json',
        html = render_html,
        xml = render_xml,
        json = render_json,
        txt = render_txt
    )
    @require_login
    def POST(self):
        check_login(self)
        table = 'cloud_host'
        data = web.input()
        try:
            uuid = data.uuid
            enable = data.enable
        except AttributeError:
            return {'message':'failed'}
        db.update(table,where="`uuid`='%s'" % uuid,enable=enable)
        return {'message':'success'}

class getDataByUUID():
    @mimerender(
        default='json',
        html = render_html,
        xml = render_xml,
        json = render_json,
        txt = render_txt
    )
    @require_login
    def POST(self):
        try:
            data = _web.input()
            uuid = data.uuid
            start_time = data.starttime
            end_time = data.endtime
        except AttributeError:
            return {'message':'failed'}
        try:
            result = db.select('cloud_result',where="`time`>='%s' and `time`<='%s' and `uuid`='%s'" % (start_time,end_time,uuid))
            if not result:
                return {'message':'db_error_no_records'}
            results = dict()
            for line in result:
                results[line['time']] = line
        except Exception:
            return {'message':'db_error'}
        return results
    
class Benchmark(object):
    def GET(self):
        return "Benchmark!"

class gateway():
    @mimerender(
        default='json',
        html = render_html,
        xml = render_xml,
        json = render_json,
        txt = render_txt
    )
    @require_login
    def POST(self):
        data = _web.input()
        if not hasattr(data,'action'):
            return {'message':'no_action'}
        else:
            if data.action == "setinterval":
                try:
                    table = 'cloud_config'
                    try:
                        interval = getattr(data,'interval')
                    except AttributeError:
                        return {'message':'attribute_error'}
                    if not int(interval)>0 or not int(interval)<3600: return {'message':'failed'}
                    try:
                        db.update(table,where="`key`='interval'",value=interval)
                    except:
                        return {'message':'db_error'}
                    return {'message':'success'}
                except:
                    return {'message':'unknow_error'}
            elif data.action == "enablebyuuid":
                try:
                    table = 'cloud_host'
                    try:
                        uuid = getattr(data,'uuid')
                        enable = getattr(data,'enable')
                    except AttributeError:
                        return {'message':'attribute_error'}
                    try:
                        db.update(table,where="`uuid`='%s'" % uuid,enable=enable)
                    except:
                        return {'message':'db_error'}
                    return {'message':'success'}
                except:
                    return {'message':'unknow_error'}
            elif data.action == "getdatabyuuid":
                pass
            else:
                return {'message':'unknow_action'}

class getMinutesByUUID():
    @mimerender(
        default='json',
        html = render_html,
        xml = render_xml,
        json = render_json,
        txt = render_txt
    )
    @require_login
    def POST(self):
        data = _web.input()
        sql =""
        table_hours = "cloud_result"
        timedate = time.strftime('%Y%m%d%H',time.localtime())
        try:
            uuid = getattr(data,'uuid')
            sql = "`uuid`='%s'" % uuid
        except AttributeError:
            return {'message':'attribute_error'}
            
        try:
            start_minute = getattr(data,'start_minute')
            end_minute = getattr(data,'end_minute')
        except Exception,e:
            print e
            sql += " and `time`>='%s'" % (timedate+'00')
            sql += " and `time`<='%s'" % (timedate+'59')
        else:
            sql += " and `time`>='%s'" % start_minute
            sql += " and `time`<='%s'" % end_minute
        ret = db.select(table_hours,where=sql).list()
        if ret:
            return {'message':ret}
        else:
            return {'message':'empty'}


class getHoursByUUID():
    @mimerender(
        default='json',
        html = render_html,
        xml = render_xml,
        json = render_json,
        txt = render_txt
    )
    @require_login
    def POST(self):
        data = _web.input()
        sql =""
        table_hours = "cloud_result_hours"
        timedate = time.strftime('%Y%m%d',time.localtime())
        try:
            uuid = getattr(data,'uuid')
            sql = "`uuid`='%s'" % uuid
        except AttributeError:
            return {'message':'attribute_error'}
            
        try:
            start_hour = getattr(data,'start_hour')
            end_hour = getattr(data,'end_hour')
        except Exception,e:
            print e
            sql += " and `time`>='%s'" % (timedate+'00')
            sql += " and `time`<='%s'" % (timedate+'23')
        else:
            sql += " and `time`>='%s'" % start_hour
            sql += " and `time`<='%s'" % end_hour
        ret = db.select(table_hours,where=sql).list()
        if ret:
            return {'message':ret}
        else:
            return {'message':'empty'}


class getDaysByUUID():
    @mimerender(
        default='json',
        html = render_html,
        xml = render_xml,
        json = render_json,
        txt = render_txt
    )
    @require_login
    def POST(self):
        data = _web.input()
        sql =""
        table_days = "cloud_result_days"
        timedate = time.strftime('%Y%m',time.localtime())
        try:
            uuid = getattr(data,'uuid')
            sql = "`uuid`='%s'" % uuid
        except AttributeError:
            return {'message':'attribute_error'}
            
        try:
            start_day = getattr(data,'start_day')
            end_day = getattr(data,'end_day')
        except Exception,e:
            print e
            sql += " and `time`>='%s'" % (timedate+'01')
            sql += " and `time`<='%s'" % (timedate+'31')
        else:
            sql += " and `time`>='%s'" % start_day
            sql += " and `time`<='%s'" % end_day
            
        ret = db.select(table_days,where=sql).list()
        if ret:
            return {'message':ret}
        else:
            return {'message':'empty'}
    
    
class getMonthByUUID():
    @mimerender(
        default='json',
        html = render_html,
        xml = render_xml,
        json = render_json,
        txt = render_txt
    )
    @require_login
    def POST(self):
        data = _web.input()
        sql =""
        table_days = "cloud_result_months"
        timedate = time.strftime('%Y',time.localtime())
        try:
            uuid = getattr(data,'uuid')
            sql = "`uuid`='%s'" % uuid
        except AttributeError:
            return {'message':'attribute_error'}
            
        try:
            start_month = getattr(data,'start_month')
            end_month = getattr(data,'end_month')
        except Exception,e:
            print e
            sql += " and `time`>='%s'" % (timedate+'01')
            sql += " and `time`<='%s'" % (timedate+'12')
        else:
            sql += " and `time`>='%s'" % start_month
            sql += " and `time`<='%s'" % end_month
            
        ret = db.select(table_days,where=sql).list()
        if ret:
            return {'message':ret}
        else:
            return {'message':'empty'}


if __name__ == '__main__':
    
    """
    logfile = '/dev/null'
    stdin = stdout = stderr = logfile
    si = open(stdin, 'r')
    so = open(stdout, 'a+')
    se = open(stderr, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())
    """
    
    try:
        application = _web.application(urls,globals()).wsgifunc()
        server = WSGIServer(('',9090),application,backlog=10000)
        server.reuse_addr = True
        server.pre_start()
        #monkey.patch_all() will replace os.fork() by gevent.fork(), so we can use multiprocessing!
        #gevent.fork()
        def serve_forever():
            server.start_accepting()
            server._stopped_event.wait()
        # start 8 process in multicore computer!
        working_process = 8
        
        for i in range(working_process - 1):
            Process(target=serve_forever, args=tuple()).start()

    except KeyboardInterrupt:
        pass
    
    
