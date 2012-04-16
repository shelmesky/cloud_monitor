#!/usr/bin/env python
import threading
import Queue
import os
import sys
import getopt
import time
import logging
import xml


try:
    import web as _web
except (ImportError,ImportWarning) as e:
    print "Can not find python-webpy, in ubuntu just run \"sudo apt-get install python-webpy\"."
    print e
    sys.exit(1)


try:
    import libvirt as _libvirt
except (ImportError,ImportWarning) as e:
    print "Can not find python-libvirt, in ubuntu just run \"sudo apt-get install python-libvirt\"."
    print e
    sys.exit(1)

_web.config.debug = False  
db = _web.database(dbn='mysql',db='cloud_monitor',user='root',pw='root')
cloud_config_table = 'cloud_config'
cloud_host_table = 'cloud_host'
cloud_result_table = 'cloud_result'

queue_host_list = Queue.Queue()  #put hostlist here
queue_result = Queue.Queue()    #put result of check here
queue_log = Queue.Queue()       #put log message here


interval_check_peroid = db.select(cloud_config_table,where="`key`='interval'").list()[0]['value'] #interval that used to check instance
interval_travelsal_libvirtd = 60 #interval that travelsal uuids from remote libvirtd

def usage():
    print """Usage: cloud_monitor_server.py [-h|--help]  [-s|--setup]  [-d|--daemon] [-r|--dryrun]
    """

try:
    options,args = getopt.getopt(sys.argv[1:],"hsdqr",["--help", "--setup","--daemon","--quit","--dryrun"])
except getopt.GetoptError,e:
    print "Given arguments was error! %s" % e
    usage()
    sys.exit(2)


if not options:
    usage()
    sys.exit(1)


for k,v in options:
    if k in("-h","--help"):
        usage()
        sys.exit(2)
    elif k in("-s","--setup"):
        setup = True
    elif k in("-d","--daemon"):
        daemon = True
    elif k in ("-s","--setup") and k in ("-d","--daemon"):
        setup = True
        daemon = True
    elif k in ("-r","--dryrun"):
        setup =  False
        daemon = False



def setup_self():
    if os.getuid() != 0:
        print "Must be root can do this setup!"
        return
    rc.local = '/etc/rc.local'
    if os.path.exists(rc.local):
        try:
            fd = open(rc.local)
        except IOError as e:
            print "Can not open file: %s" % e
        else:
            while True:
                line = fd.readlines()
                if not 'cloud_monitor' in lines:
                    pass
                if not line:
                    break
        finally:
            fd.close()


#get node value from xml format
class getNodeValue(object):
    def __init__(self,xml_file_or_string,nodes):
        import xml.dom.minidom
        self.nodes = nodes
        try:
            fd = open(xml_file_or_string)
            self.doc = xml.dom.minidom.parse(xml_file_or_string)
        except:
            self.doc = xml.dom.minidom.parseString(xml_file_or_string)
        else:
            fd.close()
        
    def get_value(self):
        node = self.nodes.split('.')
        num_of_disk = 0
        num_of_interface = 0
        vir_disks = []
        vir_interfaces = []
        if node[0]:
            node0 = self.doc.getElementsByTagName(node[0])[0]
        if node[1]:
            node1 = node0.getElementsByTagName(node[1])[0]
        for child in node1.childNodes:
            if child.nodeName == "disk":
                num_of_disk +=1
            if child.nodeName == "interface":
                num_of_interface +=1
        if node[2] and node[2]=="disk":
            for i in range(num_of_disk):
                node2 = node1.getElementsByTagName(node[2])[i]
                for n in node2.childNodes:
                    if n.nodeName == node[3]:
                        vir_disks.append(n.getAttribute(node[4]))
            return vir_disks
        if node[2] and node[2]=="interface":
            for i in range(num_of_interface):
                node2 = node1.getElementsByTagName(node[2])[i]
                for n in node2.childNodes:
                    if n.nodeName == node[3]:
                        vir_interfaces.append(n.getAttribute(node[4]))
            return vir_interfaces


#logger thread
class loginfo(threading.Thread):
    def __init__(self):
        super(loginfo,self).__init__()
        self.logger = logging.getLogger()
        self.handler = logging.FileHandler('/tmp/server.log')
        logflt = logging.Formatter("%(levelname)s [%(asctime)s]: %(message)s","%Y-%m-%d %H:%M:%S")
        self.handler.setFormatter(logflt)
        self.logger.addHandler(self.handler)
        self.daemon = False
            
    def run(self):
        levels = {"CRITICAL":50,"ERROR":40,"WARNING":30,"INFO":20,"DEBUG":10}
        while True:
            info,level = queue_log.get(True)
            for key in levels:
                    if level == key:
                            self.logger.setLevel(levels[key])
                            eval("logging."+key.lower()+"("+'"'+info.strip()+'"'+")")
                            self.logger.removeHandler(self.handler)


#make current process to daemon
def daemonize (stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
    # Do first fork.
    try: 
        pid = os.fork() 
        if pid > 0:
            sys.exit(0)   # Exit first parent.
    except OSError, e: 
        sys.stderr.write ("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror) )
        sys.exit(1)

    # Decouple from parent environment.
    os.chdir("/") 
    os.umask(0) 
    os.setsid() 

    # Do second fork.
    try: 
        pid = os.fork() 
        if pid > 0:
            sys.exit(0)   # Exit second parent.
    except OSError, e: 
        sys.stderr.write ("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror) )
        sys.exit(1)

    # Now I am a daemon!
    
    # Redirect standard file descriptors.
    si = open(stdin, 'r')
    so = open(stdout, 'a+')
    se = open(stderr, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


#libvirt client: actually do some work
class libvirt_client(object):
    def __init__(self,uri,queue):
        self.ip = uri
        self.uri = 'qemu+ssh://root@%s/system' % uri
        self.queue = queue
        self.connect()
    
    def connect(self):
        try:
            self.conn = _libvirt.open(self.uri)
        except Exception,e:
            queue_log.put((r'libvirt error: can not connect to remote libvirtd','INFO'))
    
    def check(self,uuid_string):
        result = dict()
        try:
            dom = self.conn.lookupByUUIDString(uuid_string)
        except _libvirt.libvirtError:
            db.delete(cloud_host_table,where="`uuid`='%s'" % uuid_string)
            return
        infos_first = dom.info()
        start_cputime = infos_first[4]
        start_time = time.time()
        time.sleep(3)
        infos_second = dom.info()
        end_cputime = infos_second[4]
        end_time = time.time()
        cputime = (end_cputime - start_cputime)
        time_passed = 10000000000*(end_time - start_time)*infos_second[3]
        cpu_usage = (cputime/time_passed)*100
        result['ip'] = self.ip
        result['name'] = dom.name()
        result['time'] = time.strftime('%Y%m%d%H%M',time.localtime())
        result['state'] = infos_second[0]
        result['max_memory'] = infos_second[1]
        result['memory_usage'] = infos_second[2]
        result['number_cpus'] = infos_second[3]
        result['cpu_usage'] = cpu_usage
        result['uuid_string'] = dom.UUIDString()
        
        domain_xml = dom.XMLDesc(0)
        
        vir_disks = getNodeValue(domain_xml,'domain.devices.disk.target.dev').get_value()
        disk_dict=dict()
        for disk in vir_disks:
            disk_info = dom.blockInfo(disk,0)
            disk_dict[disk]=dict()
            disk_dict[disk]['capacity'] = disk_info[0]
            disk_dict[disk]['allocation'] = disk_info[1]
            disk_dict[disk]['physical'] = disk_info[2]
        result['vir_disks'] = disk_dict
        
        vir_interfaces = getNodeValue(domain_xml,'domain.devices.interface.target.dev').get_value()
        interface_dict=dict()
        for interface in vir_interfaces:
            interface_info = dom.interfaceStats(interface)
            interface_dict[interface] = dict()
            interface_dict[interface]['rx_bytes'] = interface_info[0]
            interface_dict[interface]['rx_packets'] = interface_info[1]
            interface_dict[interface]['rx_errs'] = interface_info[2]
            interface_dict[interface]['rx_drop'] = interface_info[3]
            interface_dict[interface]['tx_bytes'] = interface_info[4]
            interface_dict[interface]['tx_packets'] = interface_info[5]
            interface_dict[interface]['tx_errs'] = interface_info[6]
            interface_dict[interface]['tx_drop'] = interface_info[7]
        result['vir_interfaces'] = interface_dict
        
        self.queue.put(result)
    
    def close(self):
        self.conn.close()


host_list = ['172.16.0.209']

#read uuids from remote libvirtd and store them to database
class thread_read_host_list(threading.Thread):
    def __init__(self):
        super(thread_read_host_list,self).__init__()
        self.daemon = False

    def run(self):
        while True:
            for host in host_list:
                dom_ids = []
                uri = 'qemu+ssh://root@%s/system' % host
                try:
                    conn = _libvirt.open(uri)
                except Exception,e:
                    queue_log.put((r'libvirt error: can not connect to remote libvirtd','INFO'))
                    break
                domain_ids = conn.listDomainsID()
                for domain_id in domain_ids:
                    dom = conn.lookupByID(domain_id)
                    dom_ids.append(dom.UUIDString())
                for uuid in dom_ids:
                    db_result = db.select(cloud_host_table,where="uuid='%s'" % uuid)
                    if not db_result.list():
                        db.insert(cloud_host_table,uuid=uuid,ip=host)
                    #queue_host_list.put((host,uuid))
            time.sleep(interval_travelsal_libvirtd)

#TODO: read host list from db (table cloud_host)
class thread_get_host_list_from_db(threading.Thread):
    def __init__(self):
        super(thread_get_host_list_from_db,self).__init__()
        self.daemon = False
    
    def run(self):
        while True:
            lists = db.select(cloud_host_table).list()
            for line in lists:
                queue_host_list.put((line['ip'],line['uuid']))
            time.sleep(int(interval_check_peroid))

# checker thread
class thread_do_check(threading.Thread):
    def __init__(self):
        super(thread_do_check,self).__init__()
        self.daemon = False
        
    def run(self):
        while True:
            uri,uuid = queue_host_list.get(True)
            virt = libvirt_client(uri,queue_result)
            virt.check(uuid)
            virt.close()


#store result to database
class thread_update_db(threading.Thread):
    def __init__(self):
        super(thread_update_db,self).__init__()
        self.daemon = False

    def run(self):
        while True:
            results = queue_result.get(True)
            db.insert(cloud_result_table,uuid=results['uuid_string'],time=results['time'],result=str(results))


def main():
    if globals()['setup']: setup_self()
    
    if globals()['daemon']:
        daemon_log_path = os.getcwd()+"/cloud_monitor_daemon.log"
        daemonize('/dev/null',daemon_log_path,daemon_log_path)
    
    pool_do_check = []
    pool_update_db = []
    num_of_do_check = 100
    num_of_update_db = 3

        
    tl = loginfo()
    tl.start()

    
    tr = thread_read_host_list()
    tr.start()
    
    tg = thread_get_host_list_from_db()
    tg.start()
    
    for i in range(num_of_do_check):
        td = thread_do_check()
        pool_do_check.append(td)
    
    for t in pool_do_check: t.start()
    
    for i in range(num_of_update_db):
        tu = thread_update_db()
        pool_update_db.append(tu)
    
    for t in pool_update_db: t.start()

if __name__ == '__main__':    
    main()


