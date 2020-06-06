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
        logging.error("Don't know how to process "+path)
    
def scan_directory(dirname, cb):
    """Right now we hard-code mbox"""
    logging.error("scan_directory(%s)",dirname)
    for (dirpath, dirnames, filenames) in os.walk(dirname):
        print(dirname)
        for fname in filenames:
            process_file( os.path.join(dirpath, fname))

def message_printer(message):
    print("{:20s} {:30s} {:40s}".format(message['date'],message['from'],message['subject']))

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
