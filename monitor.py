import threading
import time

class ThreadPoolMonitor(threading.Thread):
    """
    Moniting thread pool in every 0.5 seconds, if thread died, it will be restart.
    """
    def __init__(self, *args,**kwargs):
        super(ThreadPoolMonitor,self).__init__()
        self.daemon = False
        self.args = args
        self.kwargs = kwargs
        self.pool_list = []
    
    def run(self):
        for name,value in self.kwargs.items():
            obj = value[0]
            temp = {}
            temp[name] = obj
            self.pool_list.append(temp)
        while 1:
            #print self.pool_list
            for name,value in self.kwargs.items():
                obj = value[0]
                try:
                    parameters = value[1:]
                except:
                    died_threads = self.cal_died_thread(self.pool_list,name)
                    print "died_threads", died_threads
                    if died_threads >0:
                        for i in range(died_threads):
                            #print "start %s thread..." % name
                            t = obj[0].__class__()
                            t.start()
                            self.add_to_pool_list(t,name)
                    else:
                        break
                else:
                    died_threads = self.cal_died_thread(self.pool_list,name)
                    print "died_threads", died_threads
                    if died_threads >0:
                        for i in range(died_threads):
                            #print "start %s thread..." % name
                            t = obj[0].__class__(*parameters)
                            t.start()
                            self.add_to_pool_list(t,name)
                    else:
                        break
            time.sleep(0.5)

    def cal_died_thread(self,pool_list,name):
        i = 0
        for item in self.pool_list:
            for k,v in item.items():
                if name == k:
                    lists = v
        for t in lists:
            if not t.isAlive():
                self.remove_from_pool_list(t)
                i +=1
        return i
    
    def add_to_pool_list(self,obj,name):
        for item in self.pool_list:
            for k,v in item.items():
                if name == k:
                    v.append(obj)
    
    def remove_from_pool_list(self, obj):
        for item in self.pool_list:
            for k,v in item.items():
                try:
                    v.remove(obj)
                except:
                    pass
                else:
                    return


