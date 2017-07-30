#!/usr/bin/env python36
# encoding: utf-8
#

"""Simson's bulkmail program. None of the others seemed to work """

from __future__ import print_function

import re
import sys
import os
import datetime
import mailbox
import email.errors
import email.parser
from email.parser import BytesParser
from email import policy

import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1) # make sure sys is utf8

def sendmail(config,msg):
    if opts.dry_run:
        print("==== Will not send this message: ====\n{}\n====================\n".format(msg))
        return False
    if opts.debug:
        to = re.findall("to:.*$", msg, re.I|re.M)[0:1][0]
        print("Sending mail {}".format(to))
    from subprocess import Popen,PIPE
    p = Popen(['/usr/sbin/sendmail','-t'],stdin=PIPE)
    p.communicate(msg.encode('utf-8'))
    return True

def make_msg(config,params):
    msg = open(config['DEFAULT']['msg_file'],encoding='utf8').read()
    for a in ["%from%","%sender%","%cc%","%to%","%subject%"]:
        if a in msg:
            field = a.replace("%","")
            if field in params:
                b = params[field]
            elif field in config['DEFAULT']:
                b = config['DEFAULT'][field]
            else:
                raise RuntimeError("No {} field in config or params".format(b))
            msg = msg.replace(a,b)
    return msg

if __name__=="__main__":
    import argparse

    a = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                description="Bulk Mail Program")
    a.add_argument("--config",  help="config file with private data", default='config.ini')
    a.add_argument("--test",    help="Sends a test message to the address you specify")
    a.add_argument("--dry-run", help="do not send out email or refile messages", action="store_true")
    a.add_argument("--debug",   help="debug", action="store_true")
    a.add_argument("--addresses", help="input file for addresses")
    a.add_argument("inputs",    nargs="*")
    opts = a.parse_args()

    import configparser
    config = configparser.ConfigParser()
    config.read(opts.config)

    if opts.test:
        msg = make_msg(config,{'to':opts.test})
        if sendmail(config,msg):
            print("Message sent")
        print(msg)
        exit(1)

    if opts.addresses:
        with open(opts.addresses) as f:
            for line in f:
                name = line.strip()
                msg = make_msg(config,{'to':name})
                sendmail(config,msg)
                
