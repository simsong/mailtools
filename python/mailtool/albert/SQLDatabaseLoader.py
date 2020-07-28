"""
SQLDatabaseLoader..py:
 
An AlbertProcessor that loads a SQLite3 databsae

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

DB_SCHEMA="""CREATE TABLE MESSAGES(message_date VARCHAR(20),
                                   sender_email VARCHAR(255), 
                                   rcpt_email VARCHAR(255), 
                                   subject VARCHAR(255));"""

DB_FILE = 'database.db'         # make changable

class SQLDatabaseLoader(AbstractAlbertProcessor):
    def __init__(self, **kwargs):
        """__init__ is not required for an AbstractAlbertProcessor.
        SQLMailStats has one. It is used to create counters for the senders, subjects, and receivers.
        """
        # this is critical. If you subclass __init__(), you must call super().__init__():
        super().__init__(**kwargs) 
        self.conn = sqlite3.connect( DB_FILE ) # make the database connection
        # Create the database schema
        cursor = self.conn.cursor()
        cursor.execute(DB_SCHEMA)

    def commit(self):
        """Commit the database"""
        self.conn.commit()
        

    def process_message(self,msg):
        """This is the main method called by the Albert framework to process each message.
        Here we insert metadata for each message into the MESSAGES table.
        """
        
        def get(field):
            if field in msg:
                return msg[field]
            return None

        # Put the m message into the database
        cur = self.conn.cursor()
        try:
            cur.execute("INSERT INTO MESSAGES (message_date, sender_email, rcpt_email, subject) VALUES (?,?,?,?)",
                        (get('date'),get('from'),get('to'),get('subject')))
        except sqlite3.InterfaceError as e:
            print(e)
            print(msg)
            print("========")
            
        """Everything that follows is specific to this class and not used by Albert."""
            
