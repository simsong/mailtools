#!/usr/bin/env python36

"""This program implements an autoresponder. It's in the mailstats repository
because the responder does analysis of mail files."""

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

AUTORESPONDER_SECTION='autoresponder'

name_value_re = re.compile("[> ]*([a-zA-Z ]+): *(.*)")

def make_reply(config,msgdir):
    reply = open(config[AUTORESPONDER_SECTION]['msg_file'], mode='r', encoding='utf-8').read()
    for (key,value) in msgdir.items():
        if args.debug: print("make_reply: key={}  value={}".format(key,value))
        reply=reply.replace("%"+key+"%",value)
    reply = reply.replace("%from_address%", config['DEFAULT']['from_address'])
    reply = reply.replace("%sender_address%", config['DEFAULT']['from_address'])
    reply = reply.replace("%cc_address%", config['DEFAULT']['cc_address'])
    return reply

def sendmail(config,msg):
    if args.dry_run:
        print("==== Will not send this message: ====\n{}\n====================\n".format(msg))
        return
    if args.debug:
        print("Sending mail")
    from subprocess import Popen,PIPE
    p = Popen(['/usr/sbin/sendmail','-t'],stdin=PIPE)
    p.communicate(msg.encode('utf-8'))

def HTML_fix(msg):
    msg = msg.replace("=20"," ")
    msg = msg.replace("=3D","=")
    msg = msg.replace("&nbsp;"," ")
    print("HTML:",msg)
    return msg

def process(*,config=None,msg=None,csv_file=None):
    """Process an autoresponder request. If it can be processed, send out the message and reply True."""

    csv_file  = config[AUTORESPONDER_SECTION]['csv_file']
    msgdir = {}

    payload = msg.get_body(preferencelist=('plain','html')).get_payload()
    payload = HTML_fix(payload)         # shouldn't be necessary
    varcount = 0
    # read the input file and search for the substitution variables
    for line in payload.split("\n"):
        m = name_value_re.search(line)
        if m:
            varcount += 1
            (key,value) = m.group(1,2)
            key = key.lower()
            if args.debug:
                print("process: key={}  value={}".format(key,value))
            msgdir[key] = value

    if varcount==0:
        if args.debug:
            print("No variables found in input file; improperly formed message.")
        return False

    # make sure that the email address is actually an email address
    if "email" in msgdir:
        match = re.search(r'[._\-\w]+@[\w.\-_]+', msgdir['email'])
        if match:
            msgdir['email'] = match.group()
        else:
            del msgdir['email']

    # Now create the substituted message
    reply = make_reply(config,msgdir)
    if "%name%" in reply:
        if args.debug:
            print("Did not substitute %name% from reply")
        return False                    # no message found

    # Save the substitution variables into the CSV file
    with open(config[AUTORESPONDER_SECTION]['csv_file'],'a') as f:
        if f.tell()==0:
            # print the headers
            print("\t".join(cols), file=f)
        print("\t".join([datetime.date.today().isoformat()] + [msgdir.get(col,"") for col in cols]), file=f)
    if args.debug:
        print("process(): repl:\n{}\n".format(reply))
    if reply:
        sendmail(config,reply)
    return True


def mailmain(fname):
    with open(fname,"r") as f:
        for line in f:
            (date,name,email,domestic,undergraduates,graduates) = line.split("\t")
            print("{} <{}>".format(name,email))

if __name__=="__main__":
    import argparse

    a = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                description="Recording mail autoresponder")
    a.add_argument("--maildir", help="Input is root of Maildir", action="store_true", default=os.path.join(os.environ["HOME"],"Maildir"))
    a.add_argument("--config",  help="config file with private data")
    a.add_argument("--test",    help="print the form letter with fake data", action="store_true")
    a.add_argument("--dry-run", help="do not send out email or refile messages", action="store_true")
    a.add_argument("--debug",   help="debug", action="store_true")
    a.add_argument("--mailman",  help="turn the csv file into input for mailman")
    a.add_argument("inputs",    nargs="*")
    args = a.parse_args()

    if args.test:
        print(make_msg(config,{"name":"A professor","email":"professor@college.com"}))
        exit(1)

    if args.mailman:
        mailname(args.mailman)
        exit 0

    if not args.config:
        raise RuntimeError("--config must be specified")

    import configparser
    config = configparser.ConfigParser()
    config.read(args.config)
    cols      = config[AUTORESPONDER_SECTION]['keep_cols'].lower().replace(" ","").split(",")

    for i in args.inputs:
        if os.path.isfile(i):
            msg = BytesParser(policy=policy.default).parse(open(i,'rb'))
            process(config=config,msg=msg)
        if os.path.isdir(i):
            for fn in os.listdir(i):
                path = os.path.join(fn,fname)
                process(config=config,msg=BytesParser(policy=policy.default).parse(open(path,'rb')))
    if args.inputs:
        exit(0)


    if args.maildir:
        archive = mailbox.mbox("~/archive.mbox")
        error = mailbox.mbox("~/error.mbox")
        inbox = mailbox.Maildir("~/Maildir")
        for key in inbox.iterkeys():
            try:
                message = inbox[key]
            except email.errors.MessageParseError:
                continue
            replied = process(config=config,msg=BytesParser(policy=policy.default).parsebytes(message.as_bytes()))

            # Refile to archive or error and delete incoming message
            if not args.dry_run:
                if replied:
                    print("OK",message['subject'],message['from'])
                    archive.lock()
                    archive.add(message)
                    archive.unlock()
                else:
                    print("NOT OK",message['subject'])
                    error.lock()
                    error.add(message)
                    error.unlock()
                inbox.lock()
                inbox.discard(key)
                inbox.unlock()

