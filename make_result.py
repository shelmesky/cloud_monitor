#!/usr/bin/python
#coding:utf-8

import time
import web as _web
import sys
import getopt


# configuration for mysql database
mysql_username = "root"
mysql_password = "root"
mysql_database= "cloud_monitor"

_web.config.debug = False  # database debug option for webpy, if True it will print SQL statement in console
db = _web.database(dbn='mysql',db=mysql_database,user=mysql_username,pw=mysql_password)

def usage():
    print """Usage: %s [-h|--hours]  [-d|--days]  [-m|--months] [-y|--year]
    """ % sys.argv[0]
    sys.exit(1)

def get_virt_devs(ret,t):
    if t == "virt_disks":
        disks = list()
        rets = list()
        for line in ret:
            for rec in eval(line['result'])['vir_disks']:
                disks.append(rec)
        for disk in set(disks):
            rets.append(disk)
        return rets

    if t == "virt_interfaces":
        interfaces = list()
        rets = list()
        for line in ret:
            for rec in eval(line['result'])['vir_interfaces']:
                interfaces.append(rec)
        for interface in  set(interfaces):
            rets.append(interface)
        return rets

try:
    options,args = getopt.getopt(sys.argv[1:],"hdmy",["hours", "days","months","year"])
except getopt.GetoptError,e:
    print "Given arguments was error! %s" % e
    usage()


class make_result_weeks(object):
    pass


class make_result_months(object):
    @staticmethod
    def make(uuid):
        days = [str(y) for y in range(1,32)]
        timedate = str(int(time.strftime('%Y%m',time.localtime()))-1)
        fix_days = list()
        
        for day in days:
            if int(day)<10 and int(day)>0: day = '0'+day
            fix_days.append(day)
        
        months = dict()
        months[timedate] = dict()
        months[timedate]['uuid'] = uuid
        months[timedate]['vir_interfaces'] = dict()
        months[timedate]['vir_disks'] = dict()
        
        ret = db.select('cloud_result_days',where="`uuid`='%s' and `time` like '%s%%'" % (uuid,timedate)).list()
        
        final_results = collect_devs_status(ret,months[timedate])
        months[timedate] = final_results
        
        for month in months:
            if db.select('cloud_result_months',where="`time`='%s' and `uuid`='%s'" % (month,uuid)).list():
                db.update('cloud_result_months',where="`time`='%s' and `uuid`='%s'" % (month,uuid),result=str(months[month]))
            else:
                db.insert('cloud_result_months',time=month,uuid=uuid,result=str(months[month]))


class make_result_days(object):
    @staticmethod
    def make(uuid):
        hours = [str(y) for y in range(0,24)]
        timedate = str(int(time.strftime('%Y%m%d',time.localtime()))-1) #last day
        fix_hours = list()
        
        for hour in hours:
            if hour == '0': hour = '00'
            if int(hour)<10 and int(hour) >0: hour ='0'+hour
            fix_hours.append(hour)

        day = dict()
        day[timedate] = dict()
        day[timedate]['uuid'] = uuid
        day[timedate]['vir_interfaces'] = dict()
        day[timedate]['vir_disks'] = dict()
        
        ret = db.select('cloud_result_hours',where="`uuid`='%s' and `time` like '%s%%'" % (uuid,timedate)).list()
        
        final_results = collect_devs_status(ret,day[timedate])
        day[timedate] = final_results
        
        
        for item in day:
            if db.select('cloud_result_days',where="`time`='%s' and `uuid`='%s'" % (item,uuid)).list():
                db.update('cloud_result_days',where="`time`='%s' and `uuid`='%s'" % (item,uuid),result=str(day[item]))
            else:
                db.insert('cloud_result_days',time=item,uuid=uuid,result=str(day[item]))   


def collect_devs_status(sql_ret,store_dic):
    result = dict()
    cpu_usage = 0
    lens_of_ret = len(sql_ret)
    vir_disks = get_virt_devs(sql_ret,'virt_disks')
    vir_interfaces = get_virt_devs(sql_ret,'virt_interfaces')
    for disk in vir_disks:
        result[disk] = dict()
        result[disk]['capacity'] = result[disk]['allocation'] = result[disk]['physical'] = result[disk]['rd_req'] = 0
        result[disk]['rd_bytes'] = result[disk]['wr_req'] = result[disk]['wr_bytes'] = result[disk]['errs'] = 0
            
    for interface in vir_interfaces:
        result[interface] = dict() 
        result[interface]['rx_bytes'] = result[interface]['rx_packets'] = result[interface]['rx_errs'] = result[interface]['rx_drop'] = 0
        result[interface]['tx_bytes'] = result[interface]['tx_packets'] = result[interface]['tx_errs'] = result[interface]['tx_drop'] = 0
    
    for line in sql_ret:
        cpu_usage += eval(line['result'])['cpu_usage']
        vir_disks = eval(line['result'])['vir_disks']
            
        for disk in vir_disks:
            store_dic['vir_disks'][disk] = dict()
            for item in vir_disks[disk]:
                result[disk][item] += eval(line['result'])['vir_disks'][disk][item]
                store_dic['vir_disks'][disk][item] = result[disk][item]/lens_of_ret
            
        
        vir_interfaces = eval(line['result'])['vir_interfaces']
            
        for interface in vir_interfaces:
            store_dic['vir_interfaces'][interface] = dict()
            for item in vir_interfaces[interface]:
                result[interface][item] += eval(line['result'])['vir_interfaces'][interface][item]
                store_dic['vir_interfaces'][interface][item] = result[interface][item]/lens_of_ret
        
        real_cpu_usage = cpu_usage / lens_of_ret
        
        store_dic['cpu_usage'] = real_cpu_usage
        
    return store_dic



class make_result_hours(object):
    @staticmethod
    def make(uuid):
        minutes = [str(x) for x in range(0,59) if x%5 ==0]
        hours = [str(y) for y in range(0,24)]
        fix_minutes = list()
        fix_hours = list()
        
        for minute in minutes:
            if minute =='0': minute = '00'
            if int(minute)<10 and int(minute) >0: minute ='0'+minute
            fix_minutes.append(minute)
        
        for hour in hours:
            if hour == '0': hour = '00'
            if int(hour)<10 and int(hour) >0: hour ='0'+hour
            fix_hours.append(hour)
            
        hours_24 = dict()
        timedate = time.strftime('%Y%m%d',time.localtime())
        #timedate = '20120417'
        
        for hour in fix_hours:
            hours_24[hour] =list()
            for minute in fix_minutes:
                hours_24[hour].append((timedate+hour+minute))
        hours_24_result = dict()
        
        for key in hours_24:
            #process start for every hour
            cpu_usage_in_one_hour = 0
            ret = db.select('cloud_result',where="`time`>='%s' and `time`<='%s' and `uuid`='%s'" % (hours_24[key][0],hours_24[key][-1],uuid)).list()
            
            result = dict()
            vir_disks = get_virt_devs(ret,'virt_disks')
            vir_interfaces = get_virt_devs(ret,'virt_interfaces')
            for disk in vir_disks:
                result[disk] = dict()   
                result[disk]['capacity'] = result[disk]['allocation'] = result[disk]['physical'] = result[disk]['rd_req'] = 0
                result[disk]['rd_bytes'] = result[disk]['wr_req'] = result[disk]['wr_bytes'] = result[disk]['errs'] = 0
                
            for interface in vir_interfaces:
                result[interface] = dict()   
                result[interface]['rx_bytes'] = result[interface]['rx_packets'] = result[interface]['rx_errs'] = result[interface]['rx_drop'] = 0
                result[interface]['tx_bytes'] = result[interface]['tx_packets'] = result[interface]['tx_errs'] = result[interface]['tx_drop'] = 0
            
            #length of records in every hour
            lens_of_ret = len(ret)
            hours_24_result[key] = dict()
            hours_24_result[key]['vir_interfaces'] = dict()
            hours_24_result[key]['vir_disks'] = dict()
            
            for line in ret:
                cpu_usage_in_one_hour += eval(line['result'])['cpu_usage']
                
                
                vir_disks = eval(line['result'])['vir_disks']
                
                for disk in vir_disks:
                    hours_24_result[key]['vir_disks'][disk] = dict()
                    for item in vir_disks[disk]:
                        result[disk][item] += eval(line['result'])['vir_disks'][disk][item]
                        hours_24_result[key]['vir_disks'][disk][item] = result[disk][item]/lens_of_ret
                
                vir_interfaces = eval(line['result'])['vir_interfaces']
                
                for interface in vir_interfaces:
                    hours_24_result[key]['vir_interfaces'][interface] = dict()
                    for item in vir_interfaces[interface]:
                        result[interface][item] += eval(line['result'])['vir_interfaces'][interface][item]
                        hours_24_result[key]['vir_interfaces'][interface][item] = result[interface][item]/lens_of_ret
              
            if cpu_usage_in_one_hour != 0 and lens_of_ret != 0:
                real_cpu_usage = cpu_usage_in_one_hour/lens_of_ret
                hours_24_result[key]['cpu_usage'] = real_cpu_usage
            else:
                hours_24_result[key]['cpu_usage'] = 0

            
        sorted_result =  ([k,hours_24_result[k]] for k in sorted(hours_24_result.keys()))
        current_hour = time.strftime('%H',time.localtime())
        for line in sorted_result:
            if int(line[0]) < int(current_hour):
                if db.select('cloud_result_hours',where="`time`='%s' and `uuid`='%s'" % (str(timedate+line[0]),uuid)).list():
                    db.update('cloud_result_hours',where="`time`='%s' and `uuid`='%s'" % (str(timedate+line[0]),uuid),result=str(line[1]))
                else:
                    db.insert('cloud_result_hours',time=str(timedate+line[0]),uuid=uuid,result=str(line[1]))


def make_hours():
    timedate = time.strftime('%Y%m%d',time.localtime())
    for line in db.query("select DISTINCT(uuid) from cloud_result where `time` like '%" + timedate + "%'").list():
        make_result_hours.make(line['uuid'])

def make_days():
    timedate = str(int(time.strftime('%Y%m%d',time.localtime()))-1) #last day
    for line in db.query("select DISTINCT(uuid) from cloud_result_hours where `time` like '%" + timedate + "%'").list():
        make_result_days.make(line['uuid'])

def make_months():
    timedate = str(int(time.strftime('%Y%m',time.localtime()))-1)
    for line in db.query("select DISTINCT(uuid) from cloud_result_days where `time` like '%" + timedate + "%'").list():
        make_result_months.make(line['uuid'])

if not options: usage()

for k,v in options:
    if k in("-h","--hours"):
        make_hours()
    elif k in ("-d","--days"):
        make_days()
    elif k in ("-m","--months"):
        make_months()
    elif k in ("-y","--year"):
        make_year()
    else:
        usage()
        sys.exi(1)
    

    
