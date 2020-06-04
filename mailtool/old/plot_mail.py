#!/usr/bin/python
#
# Make some graphs about mail experiences, using privlidged access to the sqlite3 database

from collections import defaultdict
import copy
import csv
import datetime
import os
import re
import slgsql
import sqlite3
import time
import dateutil

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.dates import DateFormatter
import pandas

DB_FILE = "envelope.sqlite3"
s = slgsql.SLGSQL(DB_FILE)
c = s.conn.cursor()
LIMIT="LIMIT 1100"
LIMIT=""

ME=['simson%','slgar%','sgarf%','slg%']
NOTME=['sgarfinkel@djkeating.com','slgecr%']

def me_sql():
    stmt = f"(SELECT ROWID FROM addresses where " 
    stmt += "(" + " OR ".join([f' address like "{name}" ' for name in ME]) + ")"
    stmt += " AND "
    stmt += " (" + " AND ".join([f' address not like "{name}" ' for name in NOTME]) + ")"
    stmt += " )"
    return stmt

def show_me():
    print("Names of your emails:")
    stmt = "SELECT ROWID,address,comment FROM addresses where ROWID in "+me_sql() 
    print(stmt)
    for row in c.execute(stmt):
        print(list(row))
    

HOLIDAYS=[(dateutil.parser.parse("2017-12-25"),'Christmas'),
          (dateutil.parser.parse("2018-01-01"),'New Year\'s Day'),
          (dateutil.parser.parse("2018-02-14"),'Valentine\'s Day'),
          (dateutil.parser.parse("2018-07-04"),'Independence Day'),
          (dateutil.parser.parse("2018-07-12"),'Simson\'s Birthday')]

def doplot1(fname):
    stmt = f"select date(date_sent,'unixepoch','localtime') as date,address,subjects.subject from messages left join addresses on messages.sender=addresses.rowid left join subjects on messages.subject=subjects.rowid where date_sent > strftime('%s','now') - 60*60*24*365 order by 1 {LIMIT};"

    received_count = f"SELECT DATE(date_sent,'unixepoch') as date,count(*) FROM messages WHERE sender NOT IN {me_sql()} AND date_sent > strftime('%s','now') - 60*60*24*365 group by date;"

    data = c.execute(received_count).fetchall()
    days = [dateutil.parser.parse(d[0]) for d in data]
    messages_per_day = [d[1] for d in data]
    count_per_day = dict(zip(days,messages_per_day))

    ax = plt.subplot(111)
    plt.subplots_adjust(hspace=0, bottom=0.3)
    ax.xaxis_date()
    ax.set_xlim(left=min(days), right=max(days))
    ax.set_ylim(top=250)
    ax.set_title("Messages not sent by Simson")
    ax.bar(days, messages_per_day)
    bbox_props = dict(boxstyle="round", fc="0.8", alpha=0.7)
    arrowprops = dict(
        arrowstyle = "->",
        connectionstyle = "angle,angleA=0,angleB=90,rad=10")


    offset_x = 36
    offset_y = 200
    for (day,text) in HOLIDAYS:
        count = count_per_day[day]
        ax.annotate( f"{text} ({count})",
                     xy     = (day, count),
                     xytext = (offset_x, offset_y-count), textcoords='offset points',
                     bbox = bbox_props,
                     size = 8,
                     arrowprops=arrowprops)
        offset_y -= 15
                 
    plt.setp( ax.xaxis.get_majorticklabels(), rotation=90 )
    plt.savefig("plot.pdf")
                


if(__name__=="__main__"):
    import argparse
    parser = argparse.ArgumentParser(description='Compute file changes',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--debug",action="store_true")
    parser.add_argument("--all",action='store_true')
    parser.add_argument("--me",action='store_true',help="show who you are")
    parser.add_argument("--p")
    args = parser.parse_args()
    if args.me:
        show_me()
        exit(0)
    doplot1("output.pdf")
