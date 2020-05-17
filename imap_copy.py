#!/usr/bin/env python36
# encoding: utf-8
#

"""
A simple imap copy program that uses the config files.

[imap]
username: username
password: password
server: imap.server.to.use

"""

import re
import sys
import os
import datetime
import mailbox
import time
import email.errors
import email.parser
from email.parser import BytesParser
from email import policy
from subprocess import Popen,PIPE
import smtplib
import imaplib,socket
import configparser


# References:
# https://stackoverflow.com/questions/4179150/how-to-copy-a-message-from-one-imap-server-to-another-imap-server-using-python-i


if __name__=="__main__":
    # make sure sys is utf8
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1) 
    import argparse

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                description="IMAP mail copy program")
    parser.add_argument("--config",  help="config file with private data", default='config.ini')
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--list", action='store_true', help='list in the impa inbox')
    g.add_argument("--download", help='download the messages into a new mbox')
    g.add_argument("--upload", help='upload the messages in the inbox')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)

    # Log in to server

    try:
        M = imaplib.IMAP4_SSL(config['imap']['server'])
    except socket.gaierror:
        print("Unknown hostname:",config['imap']['server'])
        exit(1)
    M.login(config['imap']['username'], config['imap']['password'])
    M.select()

    if args.list or args.download:
        if args.download:
            if os.path.exists(args.download):
                raise FileExistsError(args.download)
            mbox = mailbox.mbox(args.download, create=True)

        typ, data = M.search(None, 'ALL')
        for num in data[0].split():
            typ, d2 = M.fetch(num, '(RFC822)')
            for val in d2:
                if type(val)==tuple:
                    (a,b) = val
                    num = a.decode('utf-8').split()[0]
                    msg = BytesParser().parsebytes(b)
                    print(msg['from'],msg['subject'],msg['date'])
                    if args.download:
                        mbox.add(msg)
    elif args.upload:
        mbox = mailbox.mbox(args.upload, create=False)
        for msg in mbox:
            M.append('Inbox', '', '', msg.as_bytes())

                        
    try:
        M.expunge()
        M.close()
        M.logout()
    except imaplib.IMAP4.     abort as e:
        #print("IMAP abort")
        pass
        
                    
