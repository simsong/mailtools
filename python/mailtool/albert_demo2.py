"""albert_demo1.py:
 
Demonstrates a AlbertProcessor.

This processor gets called for every email message in a path.  It
includes a Command Line Interface (CLI). The CLI will be moved into
another program later.

"""


import os
import re
import csv
import logging
import mailbox
import sys
import pandas as pd
from datetime import datetime
from collections import defaultdict
import calendar
import pandas as pd
import matplotlib as mpl
import matplotlib.cm as cm
import numpy as np
import matplotlib.pyplot as plt
import sqlite3
from sqlite3 import Error


assert sys.version>'3.0.0'

from albert.AbstractAlbertProcessor import AbstractAlbertProcessor
from albert.Albert import Albert


class SimpleMailStats(AbstractAlbertProcessor):
    def __init__(self, **kwargs):
        """__init__ is not required for an AbstractAlbertProcessor.
        SimpleMailStats has one. It is used to create counters for the senders, subjects, and receivers.
        """
        # this is critical. If you subclass __init__(), you must call super().__init__():
        super().__init__(**kwargs) 
        self.senders  = defaultdict(int)
        self.subjects = defaultdict(int)
        self.receivers = defaultdict(int)
        self.date = defaultdict(int)
        self.count=0
        self.i=0

    def createdb(self):
        conn = None
        try:
            conn = sqlite3.connect('database.db')
            print("DB created")
        except Error as e:
            print(e)
        if conn:
           conn.close()
        

    def insertin(self):
        conn = None
        try:
            conn = sqlite3.connect('database.db')
            
        except Error as e:
            print(e)
        cursor = conn.cursor()
        ct = '''CREATE TABLE DATA(Day VARCHAR(20), Hour INT, Result INT)'''
        cursor.execute(ct)
        conn.commit()
        print("Table created")
        cats = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for i in cats:
            a=0
            while a<24:
                cursor.execute('INSERT INTO DATA(Day, Hour, Result) values(?,?,?)',(i,a,0))
                a+=1
                conn.commit()
        print('values inserted')
        conn.close()
    
    def update(self,day,hour):
        try:
            conn = sqlite3.connect('database.db')
        except Error as e:
            print(e)
        cur = conn.cursor()
        cur.execute('SELECT Result from DATA where Day = ? and Hour = ?',(day,hour))
        val = cur.fetchall()
        for i in val:
            new_val = int(i[0])+1
        cur.execute('Update DATA SET result = ? where Day = ? and Hour = ?',(new_val,day,hour))
        conn.commit()
        cur.close()
    

    def process_message(self,msg):
        """This is the main method called by the Albert framework to process each message."""
        if 'To' in msg:
            self.receivers[ msg['To']] += 1

        if 'Cc' in msg:
            self.receivers[ msg['Cc']] += 1

        if 'From' in msg:
            try:
                self.senders[ msg['From']] += 1 
            except:
                self.senders[msg['From'].__str__()]+=1           
   
        if 'subject' in msg:
            try:    
                self.subjects[ msg['subject']] += 1
            except:
                self.subjects[msg['subject'].__str__()]+=1
        
        if 'date' in msg:
            self.date[msg['date']]+=1
            
            try:
                date=datetime.strptime(msg['date'], '%a, %d %b %Y %H:%M:%S %z (%Z)')
                day = calendar.day_name[date.weekday()]   
                hour = date.hour
                self.update(day,hour)
            except Exception as e:
                self.count+=1
        
        """Everything that follows is specific to this class and not used by Albert."""
    def printTopN(self, title, statobj, N):
        print(f"{title}:")
        counts = [(b[1],b[0]) for b in statobj.items()]
        for (ct,(value,key)) in enumerate(sorted(counts,reverse=True)):
            print(value,key)
            if ct>=N:
                break
        print("")
            
    def report(self):
        self.printTopN('Receivers',self.receivers,10)
        self.printTopN('Senders',self.senders,10)
        self.printTopN('Subjects',self.subjects,10)
        self.printTopN('Date',self.date,10)
        print(self.count)
    
    def timewheel(self):
        try:
            conn = sqlite3.connect('database.db')
        except Error as e:
            print(e)
        
        data = pd.read_sql_query('Select * from DATA',conn)
        print(data)        
#data.add_prefix('col') 
        #data['Day'] = pd.to_datetime(data['col1']).dt.day_name()        
        cats = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        data['Day'] = pd.Categorical(data['Day'], categories=cats, ordered=True)
        #data['Hour'] = data['col1']
        #print(data['Hour'],data['Day'])
        table= pd.crosstab(data.Day,data.Hour,values=data.Result,aggfunc=np.sum)
        print(table)
        n, m = table.shape
        inner_r=0.25
        color_map = cm.cool 
        normlizer = mpl.colors.Normalize(vmin = 0, vmax = 100) 
        figure, axes = plt.subplots() 
        vmin=0
        vmax=1000
        vmin= table.min().min() if vmin is None else vmin
        vmax= table.max().max() if vmax is None else vmax
        centre_circle = plt.Circle((0,0),inner_r,edgecolor='black',facecolor='white',fill=True,linewidth=0.25)
        plt.gcf().gca().add_artist(centre_circle)
#norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
#print(norm)
        cmapper = cm.ScalarMappable(norm=normlizer, cmap=color_map)
        for i, (row_name, row) in enumerate(table.iterrows()):
            labels = None if i > 0 else table.columns
            wedges = plt.pie([1] * m,radius=inner_r+float(n-i)/n, colors=[cmapper.to_rgba(x) for x in row.values], 
            labels=labels, startangle=90, counterclock=False, wedgeprops={'linewidth':-1})
            plt.setp(wedges[0], edgecolor='white',linewidth=1.5)
            wedges = plt.pie([1], radius=inner_r+float(n-i-1)/n, colors=['w'], labels=[row_name], counterclock=False, startangle=270, wedgeprops={'linewidth':0})
            plt.setp(wedges[0], edgecolor='white',linewidth=1.5)
#plt.figure(figsize=(8,8))
#plt.colorbar()
        plt.show()

    def print_message(self,message):
        if message['date'] == None:
            date = "No date"
        else:
            date = message['date']

        if message['from'] == None:
            From = "No From"
        else:
            From = message['from']

        if message['subject'] == None:
            subject = "No Subject"
        else:
            subject = message['subject']    

        print(date)
        print(From)
        print(subject)
        print("\n")


"""
Here is the initial albert cli.
It creates an Albert extractor with a SimpleMailStats as a callback,
then it asks the SimpleMailStats to print a report.
"""

if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Demo program that uses albert to scan a mailbox and print stats',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("path", nargs="*", help="Files or Directories to scan")
    args = parser.parse_args()
    sms  = SimpleMailStats()

    # Get a scanner
    sms.createdb()
    sms.insertin()
    alb = Albert(sms)  # get a scanner with the specified callback
    for p in args.path:
        alb.scan(p)             # scan
    sms.report()
    sms.timewheel()
