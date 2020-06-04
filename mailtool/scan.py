#@@ -0,0 +1,46 @@
#!/usr/bin/python
#
# Scan mail and print things about it.
# To demonstrate our initial efforts

import os
import re
import csv
import logging
import mailbox


def process_mailbox(M):#made a change here, removed extra cb variable
    for message in M:
        message_printer(message)


def process_file(path):#removed variable cb
    if path.endswith(".mbox"):
        mails = mailbox.mbox( path )
        process_mailbox(mails)
    #else:
    #    raise RuntimeError("Don't know how to process "+path)
    #commented out the else part since I stored the mbox file with some other files

def scan_directory(dirname, cb):
    """Right now we hard-code mbox"""
    logging.error("scan_directory(%s)",dirname)
    
    for (dirpath, dirnames, filenames) in os.walk(dirname):
        print(dirname)
        for fname in filenames:
            print(fname)
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
