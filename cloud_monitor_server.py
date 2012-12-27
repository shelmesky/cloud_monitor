#!/usr/bin/env python
import threading
import Queue
import os
import sys
import getopt
import time
import logging
import xml
import argparse
import signal

from cloud_monitor_settings import *
from monitor import ThreadPoolMonitor
from common.log import getlogger

from rpc_send import instance_queue
from rpc_send import loadbalanceNotify
from rpc_send import MonitorReceiver
from rpc_send import MonitorSender

logger = getlogger("CloudMonitor")

try:
    import web as _web
except (ImportError,ImportWarning) as e:
    logger.debug("Can not find python-webpy, \
           in ubuntu just run \"sudo apt-get install python-webpy\".")
    raise e

try:
    import libvirt as _libvirt
except (ImportError,ImportWarning) as e:
    logger.debug("Can not find python-libvirt, \
            in ubuntu just run \"sudo apt-get install python-libvirt\".")
    raise e

_web.config.debug = False

try:
	db = _web.database(dbn=db_engine, host=db_server, db=db_database,
									user=db_username, pw=db_password)
except Exception, e:
	logger.exception(e)
	raise e

cloud_config_table = 'cloud_config'
cloud_host_table = 'cloud_host'
cloud_result_table = 'cloud_result'

queue_host_list = Queue.Queue()  #put hostlist here
queue_result = Queue.Queue()    #put result of check here
queue_log = Queue.Queue()       #put log message here

try:
	interval_check_peroid = db.select(cloud_config_table,
								  where="`key`='interval'").list()[0]['value']
								#interval that used to check instance
except Exception, e:
	logger.exception(e)
	raise e
								
interval_travelsal_libvirtd = 60
#interval that travelsal uuids from remote libvirtd


def condition_delete_uuid(uuid):
    import shelve
    uuids_dat = 'uuids_dat.dat'
    uuid = str(uuid)
    db = shelve.open(uuids_dat,'c')
    try:
        db[uuid]
    except:
        db[uuid]=0
    if db[uuid] == 3:
        db[uuid]=0
        return True
    db[uuid] += 1
    return False
    

def setup_self():
    if os.getuid() != 0:
        print "Must be root can do this setup!"
        return
    rc_local = '/etc/rc.local'
    if os.path.exists(rc_local):
        try:
            fd = open(rc_local)
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
    def __init__(self, uri, queue, load_notify):
        self.ip = uri
        self.uri = 'qemu+tcp://%s/system' % uri
        self.queue = queue
        self.load_notify = load_notify
        self.connect()
    
    def connect(self):
        try:
            self.conn = _libvirt.open(self.uri)
        except Exception, e:
            logger.exception(e)
    
    def check(self,uuid_string):
        result = dict()
        try:
            dom = self.conn.lookupByUUIDString(uuid_string)
        except:
            logger.error("Error occurred while get dom info from %s" % uuid_string)
            ret = condition_delete_uuid(uuid_string)
            if ret:
                logger.debug("Delete nonexists uuid: %s" % uuid_string)
                db.delete(cloud_host_table,where="`uuid`='%s'" % uuid_string)
        time_sleep = 3
        infos_first = dom.info()
        start_cputime = infos_first[4]
        start_time = time.time()
        time.sleep(time_sleep)
        infos_second = dom.info()
        end_cputime = infos_second[4]
        end_time = time.time()
        cputime = (end_cputime - start_cputime)
        cores = infos_second[3]
        cpu_usage = 100 * cputime / (time_sleep*cores*1000000000)
        result['ip'] = self.ip
        result['name'] = dom.name()
        result['time'] = time.strftime('%Y%m%d%H%M',time.localtime())
        result['state'] = infos_second[0]
        result['max_memory'] = infos_second[1]
        result['memory_usage'] = infos_second[2]
        result['number_cpus'] = infos_second[3]
        result['cpu_usage'] = cpu_usage
        result['uuid_string'] = dom.UUIDString()
        
        if enable_loadbalance:
            self.load_notify.notify_loadbalance(uuid_string, cpu_usage)
        
        domain_xml = dom.XMLDesc(0)
        
        vir_disks = getNodeValue(domain_xml,
                                'domain.devices.disk.target.dev').get_value()
        disk_dict=dict()
        for disk in vir_disks:
            try:
                disk_info = dom.blockInfo(disk,0)
                disk_status_first = dom.blockStats(disk)
            except Exception, e:
                logger.error("Error occurred while get blockstatus of %s" % uuid_string)
                logger.exception(e)
                break
            disk_dict[disk]=dict()
            start_time = time.time()
            time.sleep(3)
            try:
                disk_status_second = dom.blockStats(disk)
            except Exception,e:
                logger.error("Error occurred while get blockstatus of %s" % uuid_string)
                logger.exception(e)
                break
            end_time = time.time()
            time_passed_disk = end_time - start_time
            
            disk_dict[disk]['capacity'] = disk_info[0]
            disk_dict[disk]['allocation'] = disk_info[1]
            disk_dict[disk]['physical'] = disk_info[2]
            disk_dict[disk]['rd_req'] = (disk_status_second[0] - disk_status_first[0])/time_passed_disk
            disk_dict[disk]['rd_bytes'] = (disk_status_second[1] - disk_status_first[1])/time_passed_disk
            disk_dict[disk]['wr_req'] = (disk_status_second[2] - disk_status_first[2])/time_passed_disk
            disk_dict[disk]['wr_bytes'] = (disk_status_second[3] - disk_status_first[3])/time_passed_disk
            disk_dict[disk]['errs'] = (disk_status_second[4] - disk_status_first[4])/time_passed_disk
        result['vir_disks'] = disk_dict
        
        vir_interfaces = getNodeValue(domain_xml,'domain.devices.interface.target.dev').get_value()
        interface_dict=dict()
        for interface in vir_interfaces:
            interface_info_first = dom.interfaceStats(interface)
            interface_dict[interface] = dict()
            start_time = time.time()
            time.sleep(3)
            interface_info_second = dom.interfaceStats(interface)
            end_time = time.time()
            time_passed = (end_time - start_time)
            
            interface_dict[interface]['rx_bytes'] = (interface_info_second[0]-interface_info_first[0])/time_passed
            interface_dict[interface]['rx_packets'] = (interface_info_second[1]-interface_info_first[1])/time_passed
            interface_dict[interface]['rx_errs'] = (interface_info_second[2]-interface_info_first[2])/time_passed
            interface_dict[interface]['rx_drop'] = (interface_info_second[3]-interface_info_first[3])/time_passed
            interface_dict[interface]['tx_bytes'] = (interface_info_second[4]-interface_info_first[4])/time_passed
            interface_dict[interface]['tx_packets'] = (interface_info_second[5]-interface_info_first[5])/time_passed
            interface_dict[interface]['tx_errs'] = (interface_info_second[6]-interface_info_first[6])/time_passed
            interface_dict[interface]['tx_drop'] = (interface_info_second[7]-interface_info_first[7])/time_passed
        result['vir_interfaces'] = interface_dict
        
        self.queue.put(result)
    
    def close(self):
        self.conn.close()


host_list = nova_compute_node

#read uuids from remote libvirtd and store them to database
class thread_read_host_list(threading.Thread):
    def __init__(self):
        super(thread_read_host_list,self).__init__()
        self.daemon = False

    def run(self):
        while True:
            for host in host_list:
                try:
                    dom_ids = []
                    uri = 'qemu+tcp://%s/system' % host
                    try:
                       conn = _libvirt.open(uri)
                    except Exception,e:
                        logger.exception(e)
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
                except Exception, e:
                    logger.exception(e)
                time.sleep(interval_travelsal_libvirtd)


#TODO: read host list from db (table cloud_host)
class thread_get_host_list_from_db(threading.Thread):
    def __init__(self):
        super(thread_get_host_list_from_db,self).__init__()
        self.daemon = False
    
    def run(self):
        while True:
            try:
                lists = db.select(cloud_host_table).list()
                for line in lists:
                    if int(line['enable']) == 1:
                        queue_host_list.put((line['ip'],line['uuid']))
            except Exception, e:
                logger.exception(e)
            time.sleep(int(interval_check_peroid))

# checker thread
class thread_do_check(threading.Thread):
    def __init__(self, load_notify=None):
        super(thread_do_check,self).__init__()
        self.daemon = False
        self.load_notify = load_notify
        
    def run(self):
        while True:
            try:
                uri,uuid = queue_host_list.get(True)
                virt = libvirt_client(uri, queue_result, self.load_notify)
                virt.check(uuid)
                virt.close()
            except Exception, e:
                logger.exception(e)
                raise e


#store result to database
class thread_update_db(threading.Thread):
    def __init__(self):
        super(thread_update_db,self).__init__()
        self.daemon = False

    def run(self):
        while True:
            try:
                results = queue_result.get(True)
                db.insert(cloud_result_table,uuid=results['uuid_string'],time=results['time'],result=str(results))
            except Exception, e:
                logger.exception(e)


class Watcher:   
    """this class solves two problems with multithreaded  
    programs in Python, (1) a signal might be delivered  
    to any thread (which is just a malfeature) and (2) if  
    the thread that gets the signal is waiting, the signal  
    is ignored (which is a bug).  
 
    The watcher is a concurrent process (not thread) that  
    waits for a signal and the process that contains the  
    threads.  See Appendix A of The Little Book of Semaphores.  
    http://greenteapress.com/semaphores/  
 
    I have only tested this on Linux.  I would expect it to  
    work on the Macintosh and not work on Windows.  
    """  
  
    def __init__(self):   
        """ Creates a child thread, which returns.  The parent  
            thread waits for a KeyboardInterrupt and then kills  
            the child thread.  
        """  
        self.child = os.fork()   
        if self.child == 0:   
            return  
        else:   
            self.watch()
            
    def watch(self):   
        try:   
            os.wait()   
        except (KeyboardInterrupt, SystemExit):   
            # I put the capital B in KeyBoardInterrupt so I can   
            # tell when the Watcher gets the SIGINT
            logger.debug("server exit at %s" % time.asctime())
            self.kill()   
        sys.exit()   
  
    def kill(self):   
        try:   
            os.kill(self.child, signal.SIGKILL)   
        except OSError: pass 


def main():
    parser = argparse.ArgumentParser(description="cloud monitor cli argparser")
    exclusive_group = parser.add_mutually_exclusive_group(required=False)
    
    exclusive_group.add_argument('-r', '--dryrun', action='store_true',
                            dest='dryrun', default=False, help='just dry run')
    exclusive_group.add_argument('-d', '--daemon', action='store_true',
                            dest='daemon', default=False, help='make this process go background.')
    
    sysargs = sys.argv[1:]
    args = parser.parse_args(args=sysargs)
    if len(sysargs) < 1:
        parser.print_help()
        sys.exit(1)
    else:
        if args.dryrun:
           Watcher()
        elif args.daemon:
           logger.debug("we will disappear from console :)")
           daemon_log_path = os.getcwd()+"/cloud_monitor_daemon.log"
           daemonize('/dev/null',daemon_log_path,daemon_log_path)

    load_notify = None
    # if loadbalance notify has been enabled in settings
    if enable_loadbalance:
        sender_thread = MonitorSender(instance_queue)
        sender_thread.start()

        receiver_thread = MonitorReceiver()
        receiver_thread.start()

        load_notify = loadbalanceNotify(receiver_thread)

    pool_do_check = []
    pool_update_db = []
    num_of_do_check = 100
    num_of_update_db = 3

    tr_pool = []
    for i in range(1):
        tr = thread_read_host_list()
        tr_pool.append(tr)

    for i in tr_pool:
        i.start()
        tg = thread_get_host_list_from_db()
        tg.start()
    
    for i in range(num_of_do_check):
        td = thread_do_check(load_notify)
        pool_do_check.append(td)
    
    for t in pool_do_check: t.start()
    
    for i in range(num_of_update_db):
        tu = thread_update_db()
        pool_update_db.append(tu)
    
    for t in pool_update_db: t.start()

    monitor = ThreadPoolMonitor(tr=(tr_pool,), \
            td=(pool_do_check,), \
            tu=(pool_update_db,))
    monitor.start()

if __name__ == '__main__':    
    main()


