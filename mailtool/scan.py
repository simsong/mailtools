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

assert sys.version>'3.0.0'


def process_mailbox(M, cb):
    for message in M:
        cb(message)
    

def process_file(path, cb):
    if path.endswith(".mbox"):
        mails = mailbox.mbox( path )
        process_mailbox(mails, cb)
    else:
        logging.error("Not a mbox file %s",path)
    
def scan_directory(dirname, cb):
    """Right now we hard-code mbox"""
    logging.error("scan_directory(%s)",dirname)
    for (dirpath, dirnames, filenames) in os.walk(dirname):
        print(dirname)
        for fname in filenames:
            process_file( os.path.join(dirpath, fname),cb)

def message_printer(message):
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
         
if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Extract specified variables from AHS files.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("path", nargs="*", help="Files or Directories")
    args = parser.parse_args()
    for name in args.path:
        if os.path.isdir(name):
            scan_directory(name, message_printer)
        else:
            process_file(name, message_printer)

