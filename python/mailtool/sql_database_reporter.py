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
import json

assert sys.version>'3.0.0'

class Reporter():
    def __init__(self,conn):
        self.conn = conn

    def report(self):
        obj = dict()
        queries = [("Top Senders",   "SELECT sender_email,COUNT(*) FROM MESSAGES GROUP BY sender_email ORDER BY 2 DESC LIMIT 30"),
                   ("Top Recepients","SELECT rcpt_email,COUNT(*) FROM MESSAGES GROUP BY rcpt_email ORDER BY 2 DESC LIMIT 30"),
                   ("Top Flows",     "SELECT sender_email,rcpt_email,COUNT(*) FROM MESSAGES GROUP BY sender_email,rcpt_email ORDER BY 3 DESC LIMIT 30"),
]
        for (title,sql_query) in queries:
            results = []
            print(title)
            cur = self.conn.cursor()
            cur.execute(sql_query)
            for row in cur:
                results.append(row)
                print(str(row))
            obj[title]=results
        print(json.dumps(obj,indent=4,default=str))
        

    

if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Report on the databsae',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("dbfile", help="Files or Directories to scan")
    args = parser.parse_args()
    conn = sqlite3.connect( args.dbfile )
    r = Reporter(conn)
    r.report()
