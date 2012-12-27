#coding: utf-8
#!/usr/bin/env python

import os
import sys

import pika

rabbitmq_server = "127.0.0.1"
username = "guest"
password = "guest"
virtual_host = "/"
frame_max_size = 131072 # 128 KB


def cast_to_monitor(message):
    parameters = pika.ConnectionParameters(virtual_host=virtual_host,
                                               credentials=pika.PlainCredentials(username, password),
                                               frame_max=frame_max_size,
                                               host=rabbitmq_server)
    connection = pika.BlockingConnection(parameters=parameters)
    channel = connection.channel()
    
    channel.exchange_declare(exchange='loadbalance.web',
                             type='fanout', durable=True)
    
    if isinstance(message, unicode) or isinstance(message, str):
        channel.basic_publish(exchange='loadbalance.web',
                              routing_key='',
                              body=message,
                              properties=pika.BasicProperties(delivery_mode=1))
    connection.close()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cast_to_monitor(sys.argv[1])

