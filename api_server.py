#!/usr/bin/python
from gevent import monkey
monkey.patch_all()
import os
import sys
import json
from mimerender import mimerender

try:
    import web as _web
except (ImportError,ImportWarning) as e:
    print "Can not find python-webpy, in ubuntu just run \"sudo apt-get install python-webpy\"."
    print e
    sys.exit(1)

try:
    from gevent.wsgi import WSGIServer
    import gevent
except (ImportError,ImportWarning) as e:
    print "Can not find python-gevent, in ubuntu just run \"sudo apt-get install python-gevent\"."
    print e
    sys.exit(1)
    
_web.config.debug = False

db = _web.database(dbn='mysql',db='cloud_monitor',user='root',pw='root')

render_xml = lambda message: '<message>%s</message>' % message
render_json = lambda **args: json.dumps(args)
render_html = lambda message: '<html><body>%s</body></html>' % message
render_txt = lambda message: message

urls = (
    '/setinterval','setInterval',
    '/enablebyuuid','enableByUUID',
    '/getdatabyuuid','getDataByUUID',
    '/gateway','gateway',
    '/benchmark','Benchmark'
)

class setInterval():
    @mimerender(
        default = 'json',
        html = render_html,
        xml  = render_xml,
        json = render_json,
        txt  = render_txt
    )
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
    def POST(self):
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
        server = WSGIServer(('',8080),application,backlog=10000)
        server.reuse_addr = True
        server.pre_start()
        gevent.fork()
        server.start_accepting()
        server._stopped_event.wait()
    except KeyboardInterrupt:
        pass
    
    