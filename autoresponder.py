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
import smtplib
from email.parser import BytesParser
from email import policy

AUTORESPONDER_SECTION='autoresponder'
USE_SENDMAIL=False

name_value_re = re.compile("[> ]*([a-zA-Z ]+): *(.*)")

def make_reply(config,msgdict):
    reply = open(config[AUTORESPONDER_SECTION]['msg_file'], mode='r', encoding='utf-8').read()
    for (key,value) in msgdict.items():
        if args.debug: print("make_reply: key={}  value={}".format(key,value))
        reply=reply.replace("%"+key+"%",value)
    reply = reply.replace("%from_address%", config['autoresponder']['from_address'])
    reply = reply.replace("%sender_address%", config['autoresponder']['from_address'])
    reply = reply.replace("%cc_address%", config['autoresponder']['cc_address'])
    return reply

def sendmail(*,config,from_addr,to_addrs,msg):
    if args.dry_run:
        print("==== Will not send this message: ====\n{}\n====================\n".format(msg))
        return
    if args.debug:
        print("Sending mail")

    if USE_SENDMAIL:
        from subprocess import Popen,PIPE
        p = Popen(['/usr/sbin/sendmail','-t'],stdin=PIPE)
        p.communicate(msg.encode('utf-8'))
        return True;

    host = config['smtp']['server']
    with smtplib.SMTP(host,587) as smtp:
        if args.debug:
            smtp.set_debuglevel(1)
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(config['smtp']['username'],config['smtp']['password'])
        smtp.sendmail(from_addr,to_addrs,msg)
        print("Send mail to ",to_addrs," from ",from_addr," with SMTP . message length:",len(msg))
    

def HTML_unquote(msg):
    msg = msg.replace("=20"," ")
    msg = msg.replace("=3D","=")
    msg = msg.replace("&nbsp;"," ")
    return msg

def process(*,config=None,msg=None,csv_file=None):
    """Process an autoresponder request. If it can be processed, send out the message and reply True."""

    if args.debug:
        print("======================= process ====================")

    csv_file  = config[AUTORESPONDER_SECTION]['csv_file']
    to_addr = None
    msgdict = {}

    payload = msg.as_string()
    payload = HTML_unquote(payload)         # shouldn't be necessary
    varcount = 0
    # read the input file and search for the substitution variables
    for line in payload.split("\n"):
        if "<" in line:                 # easy way to avoid HTML 
            continue
        m = name_value_re.search(line)
        if m:
            varcount += 1
            (key,value) = m.group(1,2)
            key = key.lower()
            if args.debug:
                print("process: key={}  value={}".format(key,value))
            msgdict[key] = value

    if varcount==0:
        if args.debug:
            print("No variables found in input file; improperly formed message.")
        return False

    # make sure that the email address is actually an email address
    if "email" in msgdict:
        match = re.search(r'[._\-\w]+@[\w.\-_]+', msgdict['email'])
        if match:
            msgdict['email'] = to_addr = match.group()
        else:
            del msgdict['email']

    # Now create the substituted message
    reply = make_reply(config,msgdict)
    if "%name%" in reply:
        if args.debug:
            print("Did not substitute %name% from reply")
        return False                    # no message found

    # Save the substitution variables into the CSV file
    with open(config[AUTORESPONDER_SECTION]['csv_file'],'a') as f:
        if f.tell()==0:
            # print the headers
            print("\t".join(cols), file=f)
        print("\t".join([datetime.date.today().isoformat()] + [msgdict.get(col,"") for col in cols]), file=f)
    if args.debug:
        print("process(): repl:\n{}\n".format(reply))
    if reply:
        sendmail(config=config,to_addrs=[to_addr,config['autoresponder']['cc_address']],
                 from_addr=config['autoresponder']['from_address'],msg=reply)
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
    a.add_argument("--maildir", help="Input is root of Maildir", action="store_true")
    a.add_argument("--imap",    help="Input is imap as specified in config file", action='store_true')
    a.add_argument("--config",  help="config file with private data")
    a.add_argument("--test",    help="print the form letter with fake data", action="store_true")
    a.add_argument("--mailtest", help="Send a test mail message to the address provided.")
    a.add_argument("--dry-run", help="do not send out email or refile messages", action="store_true")
    a.add_argument("--debug",   help="debug", action="store_true")
    a.add_argument("--mailman",  help="turn the csv file into input for mailman")
    args = a.parse_args()

    if args.test:
        print(make_msg(config,{"name":"A professor","email":"professor@college.com"}))
        exit(1)

    if args.mailman:
        mailname(args.mailman)
        exit(0)

    if not args.config:
        raise RuntimeError("--config must be specified")

    import configparser
    config = configparser.ConfigParser()
    config.read(args.config)
    cols      = config[AUTORESPONDER_SECTION]['keep_cols'].lower().replace(" ","").split(",")

    if args.mailtest:
        msgdict = {'name':'test name',
                   'email':args.mailtest}
        reply = make_reply(config,msgdict)
        sendmail(config=config,to_addrs=[args.mailtest],from_addr=config['autoresponder']['from_address'],msg=reply)
        exit(1)

    archive = mailbox.mbox("~/archive.mbox")
    error = mailbox.mbox("~/error.mbox")
    if args.maildir:
        inbox = mailbox.Maildir("~/Maildir")
        for key in inbox.iterkeys():
            try:
                message = inbox[key]
            except email.errors.MessageParseError:
                continue
            msg = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
            replied = process(config=config,msg=msg)

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

    if args.imap:
        import imaplib,socket
        try:
            M = imaplib.IMAP4_SSL(config['imap']['server'])
        except socket.gaierror:
            print("Unknown hostname:",config['imap']['server'])
            exit(1)
        M.login(config['imap']['username'], config['imap']['password'])
        M.select()
        typ, data = M.search(None, 'ALL')
        for num in data[0].split():
            typ, d2 = M.fetch(num, '(RFC822)')
            for val in d2:
                if type(val)==tuple:
                    (a,b) = val
                    num = a.decode('utf-8').split()[0]
                    msg = BytesParser().parsebytes(b)
                    replied = process(config=config,msg=msg)
                    # Refile to archive or error and delete incoming message
                    if not args.dry_run:
                        if replied:
                            archive.lock()
                            archive.add(msg)
                            archive.unlock()
                        else:
                            error.lock()
                            error.add(msg)
                            error.unlock()
                        M.store(num, '+FLAGS', '\\Deleted')
        try:
            M.expunge()
            M.close()
            M.logout()
        except imaplib.IMAP4.     abort as e:
            #print("IMAP abort")
            pass
        
                    
