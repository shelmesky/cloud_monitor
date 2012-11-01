
# configuration for cloud_monitor and etc...
db_engine = 'mysql'
db_server = '127.0.0.1'
db_username = 'root'
db_password ='root'
db_database = 'cloud_monitor'

api_server_port = 8080

nova_compute_node = ['10.0.200.1']

# configuration for RabbitMQ Server
rabbitmq_server = "127.0.0.1"
username = "guest"
password = "guest"
virtual_host = "/"
frame_max_size = 131072 # 128 KB

# configuration for loadbalance server
loadbalance_server = 'http://127.0.0.1:8888'