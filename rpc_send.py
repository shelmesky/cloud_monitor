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

monitor_queue = Queue.Queue()


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
        AdminReceiver._lock.acquire()
        if not cls._instance:
            cls._instance = super(AdminReceiver,cls).__new__(
                cls, *args, **kwargs)
        AdminReceiver._lock.release()
        return cls._instance
    
    def __init__(self, queue):
        super(MonitorSender, self).__init__()
        self.daemon = False
        self.instance_queue = queue
    
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
            message = self.instance_queue.get()
            self.channel_server.basic_publish(exchange='loadbalance.monitor',
                                              routing_key='',
                                              body=simplejson.dumps(message),
                                              properties=pika.BasicProperties(
                                                delivery_mode=1,
                                              ))
    
class MonitorReceiver(threading.Thread):
    """
    receive instance uuid from web client, and maintain the instance_list.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(self, *args, **kwargs):
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
                                               credentials=pika.PlainCredentials(username,passowrd),
                                               frame_max=frame_max,
                                               host=rabbitmq_server)
        
        select_connection.POLLER_TYPE = 'epoll'
        self.connection_web = select_connection.SelectConnection(parameers=parameters,
                                                                 on_open_callback=self.on_connected)
        
    def run(self):
        """
        start event loop, and wait for message from web client.
        """
        self.connection_web.ioloop.start()
    
    def on_connected(self, _connection):
        connection.channel(self.on_channel_open)
    
    def on_channel_open(self, _channel):
        self.channel_web = _channel
        self.channel_web.exchange_declare(exchange='loadbalance.web',
                                          type='fanout', durable=True,
                                          callback=self.on_exchange_declare)
    
    def on_exchange_declared(self, _exchange):
        self.channel_web.queue_declare(durable=False, exclusive=True,
                                       callback=self.on_queue_declared)
    
    def on_queue_delcared(self, _result):
       self.queue_name = _result.method.queue
       self.channel_seb.queue_bind(exchange='loadbalance.web',
                                   queue=self.queue_name,
                                   callback=self.on_queue_bind)
    
    def on_queue_bind(self, _frame):
        self.channel_web.basic_consume(self.handle_delivery,
                                       queue=self.queue_name)
    
    def handle_delivery(self, ch, method, header, body):
        """
        callback function that will receive return message from web client.
        """
        if not isinstance(body, unicode) or not isinstance(body, str):
            raise RuntimeError("message from web client is not unicode string.")
        self.instance_list.add(body)
    
    @property
    def get_instancelist(self):
        return list(self.instance_list)

def getListInstance():
    return http_api.listinstance()
