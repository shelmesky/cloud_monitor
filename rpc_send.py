#coding: utf-8
#!/usr/bin/env python
import os
import sys
import threading
import Queue
import simplejson

import pika
from pika.adapters import select_connection

from cloud_monitor_settings import *
from common import http_api

instance_queue = Queue.Queue()


class MonitorSender(threading.Thread):
    """
    send alert message to loadbalance server.
    """
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """
        singleton model
        """
        MonitorSender._lock.acquire()
        if not cls._instance:
            cls._instance = super(MonitorSender,cls).__new__(
                cls, *args, **kwargs)
        MonitorSender._lock.release()
        return cls._instance
    
    def __init__(self, queue):
        super(MonitorSender, self).__init__()
        self.daemon = False
        self.instance_queue = queue
        self.connect()
    
    def connect(self):
        parameters = pika.ConnectionParameters(virtual_host=virtual_host,
                                               credentials=pika.PlainCredentials(username, password),
                                               frame_max=frame_max_size,
                                               host=rabbitmq_server)
        
        select_connection.POLLER_TYPE = 'epoll'
        self.connection_server = select_connection.SelectConnection(parameters=parameters,
                                                                    on_open_callback=self.on_connected)
        
    def run(self):
        self.connection_server.ioloop.start()
    
    def on_connected(self, _connection):
        _connection.set_backpressure_multiplier(20000)
        _connection.channel(self.on_channel_open)
    
    def on_channel_open(self, _channel):
        self.channel_server = _channel
        self.channel_server.exchange_declare(exchange='loadbalance.monitor',
                                             type='fanout', durable=True,
                                             callback=self.on_queue_declared)
    
    def on_queue_declared(self, frame):
        while 1:
            uuid = self.instance_queue.get()
            self.channel_server.basic_publish(exchange='loadbalance.monitor',
                                              routing_key='',
                                              body=uuid,
                                              properties=pika.BasicProperties(
                                                delivery_mode=1,
                                              ))
    
class MonitorReceiver(threading.Thread):
    """
    receive instance uuid from web client, and maintain the instance_list.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """
        singleton model.
        """
        MonitorReceiver._lock.acquire()
        if not cls._instance:
            cls._instance = super(MonitorReceiver, cls).__new__(cls,
                                                            *args, **kwargs)
        MonitorReceiver._lock.release()
        return cls._instance
    
    def __init__(self):
        super(MonitorReceiver, self).__init__()
        self.daemon = False
        ins_list = getListInstance()
        self.instance_list = set()
        map(self.instance_list.add, ins_list)
        self.connect()
    
    def connect(self):
        """
        connect to rabbit server
        """
        parameters = pika.ConnectionParameters(virtual_host=virtual_host,
                                               credentials=pika.PlainCredentials(username, password),
                                               frame_max=frame_max_size,
                                               host=rabbitmq_server)
        
        select_connection.POLLER_TYPE = 'epoll'
        self.connection_web = select_connection.SelectConnection(parameters=parameters,
                                                                 on_open_callback=self.on_connected)
        
    def run(self):
        """
        start event loop, and wait for message from web client.
        """
        self.connection_web.ioloop.start()
    
    def on_connected(self, _connection):
        _connection.channel(self.on_channel_open)
    
    def on_channel_open(self, _channel):
        self.channel_web = _channel
        self.channel_web.exchange_declare(exchange='loadbalance.web',
                                          type='fanout', durable=True,
                                          callback=self.on_exchange_declared)
    
    def on_exchange_declared(self, _exchange):
        self.channel_web.queue_declare(durable=False, exclusive=True,
                                       callback=self.on_queue_declared)
    
    def on_queue_declared(self, _result):
       self.queue_name = _result.method.queue
       self.channel_web.queue_bind(exchange='loadbalance.web',
                                   queue=self.queue_name,
                                   callback=self.on_queue_bind)
    
    def on_queue_bind(self, _frame):
        self.channel_web.basic_consume(self.handle_delivery,
                                       queue=self.queue_name)
    
    def handle_delivery(self, ch, method, header, body):
        """
        callback function that will receive return from web client.
        """
        if not isinstance(body, unicode) and not isinstance(body, str):
            raise RuntimeError("message from web client is not unicode string.")
        self.instance_list.add(body)
    
    @property
    def get_instancelist(self):
        return list(self.instance_list)


def getListInstance():
    return http_api.listinstance()


class loadbalanceNotify(object):
    """
    get instance list from the web client,
    and check cpu usage of them, if it exceed the threshold,
    put the uuid to instance_queue.
    """
    def __init__(self, receiver):
        # get instance list from MonitorReceiver
        self.instance_list = receiver.get_instancelist
        self.exceed_threshold = {}

    def notify_loadbalance(self, uuid, cpu_usage):
        if self.exceed_threshold.get(uuid, None) >= 5:
            self.exceed_threshold[uuid] = 0
            # send uuid to instance_queue
            instance_queue.put(uuid)
        if uuid in self.instance_list:
            if uuid in self.exceed_threshold:
                if int(cpu_usage) > notify_threshold:
                    self.exceed_threshold[uuid] += 1
            else:
                self.exceed_threshold[uuid] = 0


if __name__ == '__main__':
    # make a test
    sender_thread = MonitorSender(instance_queue)
    sender_thread.start()
    
    receiver_thread = MonitorReceiver()
    receiver_thread.start()
    
    import time
    load_notify = loadbalanceNotify(receiver_thread)
    while 1:
        print "send notify"
        load_notify.notify_loadbalance("0084afec-950e-4132-a64c-f2342c34f85c", 100)
        time.sleep(2)

