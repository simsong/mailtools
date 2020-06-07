#!/usr/bin/python
#
# Scan mail and print things about it.
# To demonstrate our initial efforts

import os
import re
import csv
import logging
import mailbox
import sys

from collections import defaultdict

assert sys.version>'3.0.0'

class MailStats:
    def __init__(self):
        self.senders  = defaultdict(int)
        self.subjects = defaultdict(int)
        self.receivers = defaultdict(int)

    def printTopN(self, title, statobj, N):
        print(f"{title}:")
        counts = [(b[1],b[0]) for b in statobj.items()]
        for (ct,(value,key)) in enumerate(sorted(counts,reverse=True)):
            print(value,key)
            if ct>=N:
                break
        print("")
            

    def process_message(self,msg):
        if 'To' in msg:
            self.receivers[ msg['To']] += 1
        if 'Cc' in msg:
            self.receivers[ msg['Cc']] += 1
        if 'From' in msg:
            self.senders[ msg['To']] += 1            
        if 'Subject' in msg:
            self.subjects[ msg['Subject']] += 1

    def report(self):
        self.printTopN('Receivers',self.receivers,10)
        self.printTopN('Senders',self.senders,10)
        self.printTopN('Subjects',self.subjects,10)
        

def process_mailbox(M, cb):
    for message in M:
        cb(message)
    
def process_file(path, cb):
    if path.endswith(".mbox"):
        mails = mailbox.mbox( path )
        process_mailbox(mails, cb)
    else:
        logging.error("Don't know how to process "+path)
    
def scan_directory(dirname, cb):
    """Right now we hard-code mbox"""
    logging.error("scan_directory(%s)",dirname)
    for (dirpath, dirnames, filenames) in os.walk(dirname):
        print(dirname)
        for fname in filenames:
            process_file( os.path.join(dirpath, fname), cb)

def message_printer(message):
    print("{:20s} {:30s} {:40s}".format(message['date'],message['from'],message['subject']))

if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Extract specified variables from AHS files.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("path", nargs="*", help="Files or Directories")
    args = parser.parse_args()
    ms = MailStats()
    for name in args.path:
        if os.path.isdir(name):
            scan_directory(name, ms.process_message)
        else:
            process_file(name, ms.process_message)
    ms.report()
