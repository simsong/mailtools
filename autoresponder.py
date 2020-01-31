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
import configparser
import logging
from email.parser import BytesParser
from email import policy
import quopri

AUTORESPONDER_SECTION='autoresponder'
USE_SENDMAIL=False

## Logging

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILENAME = '/home/m57_mail/logfile.txt'
logging.basicConfig(filename=LOG_FILENAME, level=logging.DEBUG, format=LOG_FORMAT)

name_value_re = re.compile("[> ]*([a-zA-Z ]+): *(.*)")

def make_reply(config,msgvars):
    reply = open(config[AUTORESPONDER_SECTION]['msg_file'], mode='r', encoding='utf-8').read()
    for (key,value) in msgvars.items():
        if args.debug: print("make_reply: key={}  value={}".format(key,value))
        reply=reply.replace("%"+key+"%",value)
    reply = reply.replace("%from_address%", config['autoresponder']['from_address'])
    reply = reply.replace("%sender_address%", config['autoresponder']['from_address'])
    reply = reply.replace("%cc_address%", config['autoresponder']['cc_address'])
    return reply

def send_message(*,config,from_addr,to_addrs,msg):
    if not isinstance(from_addr,str):
        raise ValueError("from_addr is {} type {}".format(from_addr,type(from_addr)))

    for (count,to) in enumerate(to_addrs):
        if not isinstance(to,str):
            raise ValueError("to_addrs[{}] is {} type {}".format(count,to,type(to)))

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
        smtp.sendmail(from_addr,to_addrs,msg.encode('utf8'))
        print("Send mail to ",to_addrs," from ",from_addr," with SMTP . message length:",len(msg))
    

def clean_email(email):
    m = re.search(r'([._\-\w]+@[\w.\-_]+)', email)
    if not m:
        raise ValueError("no email address found in '{}'".format(email))
    return m.group(1)

# https://stackoverflow.com/questions/14694482/converting-html-to-text-with-python
from html.parser import HTMLParser
class HTMLFilter(HTMLParser):
    text = ""
    def handle_data(self, data):
        self.text += data

def get_msg_text(msg):
    """Return the text of a message, conveting HTML if necessar"""

    #for part in msg.walk():
    #    print(part.get_content_type())
    #text =  msg.get_content()
    # https://docs.python.org/3.7/library/email.message.html#email.message.EmailMessage
    text = msg.get_body(preferencelist=('plain','html')).get_content()
    if text.startswith("<html"):
        f = HTMLFilter()
        f.feed( text.replace("</div>","</div>\n").replace("<br","\n<br") )
        return f.text
    return text

def process_msg(*,config,msg):
    """Process an autoresponder request. If it can be processed, send out the message and reply True."""


    if args.debug:
        print("======================= process ====================")

    csv_file  = config[AUTORESPONDER_SECTION]['csv_file']
    msgvars = {}                            # variables that get substituted in message

    text  = get_msg_text(msg)
    lines = text.split("\n")
    if args.debug:
        print("source message:")
        for (ct,line) in enumerate(lines):
            print(ct,line)
        print("------------------------------------------------")

    # read the input file and search for the substitution variables
    for line in lines:
        m = name_value_re.search(line)
        if not m:
            continue
        (key,value) = m.group(1,2)
        key = key.lower()
        value = value.strip()
        if value:
            if args.debug:
                print("process_msg: FOUND VARIABLE {} = {}".format(key,value))
            if key=='email':
                msgvars[key] = str(clean_email(value))
            else:
                msgvars[key] = str(value)

    if len(msgvars)==0:
        raise RuntimeError("Could not find substitution variables in input message")

    if "email" not in msgvars:
        print(msg,file=sys.stderr)
        print("----------------",file=sys.stderr)
        for (k,v) in msgvars.items():
            print(f"{k}:{v}",file=sys.stderr)
        raise RuntimeError("input message did not define an email address")

    if "name" not in msgvars:
        raise RuntimeError("input message did not define a name")

    # Save the substitution variables into the CSV file
    with open(config[AUTORESPONDER_SECTION]['csv_file'],'a', encoding='utf-8', errors='ignore') as f:
        if f.tell()==0:
            # print the headers
            print("\t".join(cols), file=f)
        line = "\n".join([datetime.date.today().isoformat()] + [msgvars.get(col,"") for col in cols])
        f.write(line+"\n")

    to_addrs = [msgvars['email'], config['autoresponder']['cc_address']]
    reply = make_reply(config, msgvars)
    send_message(config=config,
                     from_addr=config['autoresponder']['from_address'],
                     to_addrs = to_addrs,
                     msg=reply)



def process_maildir(config):
    inbox = mailbox.Maildir("~/Maildir")
    for key in inbox.iterkeys():
        try:
            message = inbox[key]
        except email.errors.MessageParseError:
            continue
        msg = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
        replied = process_msg(config=config,msg=msg)

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

def process_imap(config):
    import imaplib,socket
    try:
        if args.debug:
            print("Connecting to ",config['imap']['server'])
        M = imaplib.IMAP4_SSL(config['imap']['server'])
    except socket.gaierror:
        print("Unknown hostname:",config['imap']['server'])
        exit(1)
    M.login(config['imap']['username'], config['imap']['password'])
    M.select()
    typ, data = M.search(None, 'ALL')
    if args.debug:
        print("typ=",typ)
        print("data=",data)
    for num in data[0].split():
        if args.debug:
            print("Fetch",num)
        typ, d2 = M.fetch(num, '(RFC822)')
        for val in d2:
            if type(val)==tuple:
                (a,b) = val
                num = a.decode('utf-8').split()[0]
                msg = BytesParser(policy=policy.default).parsebytes(b)
                replied = process_msg(config=config,msg=msg)
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
        if args.debug:
            print("IMAP abort")
            print(e)
        pass
        
                    
    

def mailmain(fname):
    with open(fname,"r") as f:
        for line in f:
            (date,name,email,domestic,undergraduates,graduates) = line.split("\t")
            print("{} <{}>".format(name,email))

if __name__=="__main__":
    logging.info("Starting Up {}".format(sys.argv))

    import argparse
    a = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                description="Recording mail autoresponder")
    a.add_argument("--maildir", help="Input is root of Maildir", action="store_true")
    a.add_argument("--imap",    help="Input is imap as specified in config file", action='store_true')
    a.add_argument("--config",  help="config file with private data", default='config.ini')
    a.add_argument("--test",    help="print the form letter with fake data", action="store_true")
    a.add_argument("--mailtest", help="Send a test mail message to the address provided.")
    a.add_argument("--dry-run", help="do not send out email or refile messages", action="store_true")
    a.add_argument("--debug",   help="debug", action="store_true")
    a.add_argument("--mailman",  help="turn the csv file into input for mailman")
    args = a.parse_args()

    if args.mailman:
        mailname(args.mailman)
        exit(0)

    config = configparser.ConfigParser()
    config.read(args.config)
    cols      = config[AUTORESPONDER_SECTION]['keep_cols'].lower().replace(" ","").split(",")

    if args.test:
        print(make_reply(config,{"name":"A professor","email":"professor@college.com"}))
        exit(1)

    if args.mailtest:
        msgvars = {'name':'test name',
                   'email':args.mailtest}
        reply = make_reply(config,msgvars)
        send_message(config=config,
                         to_addrs=[args.mailtest],
                         from_addr=config['autoresponder']['from_address'],
                         msg=reply)
        exit(1)

    archive = mailbox.mbox("~/archive.mbox")
    error = mailbox.mbox("~/error.mbox")
    if args.maildir:
        process_maildir(config)
        
    if args.imap:
        process_imap(config)
