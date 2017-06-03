#!/usr/bin/env python36

"""This program implements an autoresponder. It's in the mailstats repository
because the responder does analysis of mail files."""

from __future__ import print_function

import re
import sys
import os
import datetime

name_value_re = re.compile("> ([a-zA-Z ]+): *(.*)")

def make_msg(config,msgdir):
    msg = open(config['DEFAULT']['msg_file']).read()
    for (key,value) in msgdir.items():
        msg=msg.replace("%"+key+"%",value)
    msg = msg.replace("%from_address%", config['DEFAULT']['from_address'])
    msg = msg.replace("%sender_address%", config['DEFAULT']['from_address'])
    msg = msg.replace("%cc_address%", config['DEFAULT']['cc_address'])
    return msg

def process(config,infile):
    """Process an autoresponder request. If it can be processed, return the new message to send out.
    Otherwise return None"""
    msgdir = {}
    # read the input file and search for the substitution variables
    for line in infile.split("\n"):
        m = name_value_re.search(line)
        if m:
            msgdir[m.group(1).lower()] = m.group(2)
    # Save the substitution variables into the CSV file
    with open(config['DEFAULT']['csv_file'],'a') as f:
        if f.tell()==0:
            # print the headers
            print("\t".join(cols),file=f)
        print("\t".join([datetime.date.today().isoformat()] + [msgdir.get(col.lower(),"") for col in cols]),file=f)
    # Now create the substituted message
    repl = make_msg(config,msgdir)
    if "%name%" not in repl:
        return repl
    return None

def sendmail(config,msg):
    from subprocess import Popen,PIPE
    p = Popen(['/usr/sbin/sendmail','-t'],stdin=PIPE)
    p.communicate(msg.encode('utf-8'))

    

if __name__=="__main__":
    import argparse

    a = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                description="Recording mail autoresponder")
    a.add_argument("--maildir", help="Input is root of Maildir", action="store_true", default=os.path.join(os.environ["HOME"],"Maildir"))
    a.add_argument("--config",  help="config file with private data")
    a.add_argument("--test",    help="print the form letter with fake data", action="store_true")
    a.add_argument("--dry-run", help="do not send out email", action="store_true")
    a.add_argument("inputs",    nargs="*")
    opts = a.parse_args()

    if opts.test:
        print(make_msg(config,{"name":"A professor","email":"professor@college.com"}))
        exit(1)

    if opts.config:
        import configparser
        config = configparser.ConfigParser()
        config.read(opts.config)
        
        csv_file  = config['DEFAULT']['csv_file']
        cols      = config['DEFAULT']['keep_cols'].replace(" ","").split(",")
    else:
        raise RuntimeError("--config must be specified")

    if opts.maildir:
        import mailbox
        import email.errors
        import email.parser
        inbox = mailbox.Maildir("~/Maildir")
        #archive = mailbox.Maildir("~/Maildir/.Responded")
        #error = mailbox.Maildir("~/Maildir/.Error")
        archive = mailbox.mbox("~/archive.mbox")
        error = mailbox.mbox("~/error.mbox")
        for key in inbox.iterkeys():
            try:
                message = inbox[key]
            except email.errors.MessageParseError:
                continue
            m = email.message_from_string(message.as_string())
            msg = m.as_string()
            msg = msg.replace("=20"," ")
            rmesg = process(config,msg)
            if rmesg:
                print("OK",m['subject'])
                sendmail(config,rmesg)
                archive.lock()
                archive.add(message)
                archive.unlock()
            else:
                print("NOT OK",m['subject'])
                error.lock()
                error.add(message)
                error.unlock()
            inbox.lock()
            inbox.discard(key)
            inbox.unlock()

    for fn in opts.inputs:
        if os.path.isfile(fn):
            process(config,open(fn))
        if os.path.isdir(fn):
            for fname in os.listdir(fn):
                process(config,open(os.path.join(fn,fname)))
