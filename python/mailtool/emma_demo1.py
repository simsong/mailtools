"""albert_demo1.py:
 
Demonstrates a Emma Analysis


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

DB_FILE = 'database.db'         # make changable

class EmmaProcessor:
    def __init__(self, **kwargs):
        """__init__ is not required for an AbstractAlbertProcessor.
        SQLMailStats has one. It is used to create counters for the senders, subjects, and receivers.
        """
        # this is critical. If you subclass __init__(), you must call super().__init__():
        super().__init__(**kwargs) 
        self.conn = sqlite3.connect( DB_FILE ) # make the database connection

    def report(self):
        queries = [("Top Senders","SELECT sender_email,COUNT(*) FROM MESSAGES GROUP BY sender_email ORDER BY 2 DESC LIMIT 10")]
        for (title,sql_query) in queries:
            print(title)
            cur = self.conn.cursor()
            cur.execute(sql_query)
            for row in cur:
                print(str(row))
        
    
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


"""
Here is the initial albert cli.
It creates an Albert extractor with a SQLMailStats as a callback,
then it asks the SQLMailStats to print a report.
"""

if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Demo program that uses albert to scan a mailbox and print stats',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("path", nargs="*", help="Files or Directories to scan")
    args = parser.parse_args()

    # Open the database
    # Do some selects
    # Print the results
    ep = EmmaProcessor()
    ep.report()
