#!/usr/bin/python

import getpass
import imaplib
import email
import re

list_response_pattern = re.compile(
    r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)'
)


def parse_list_response(line):
    match = list_response_pattern.match(line.decode('utf-8'))
    flags, delimiter, mailbox_name = match.groups()
    mailbox_name = mailbox_name.strip('"')
    return (flags, delimiter, mailbox_name)


def login(opts,config):
    host = config["imap"]["host"]
    user = config["imap"]["user"]
    print("host: ",host)
    print("user: ",user)

    try:
        pw = config["imap"]["pass"]
    except KeyError:
        pw = getpass.getpass()

    #M = imaplib.IMAP4(host)
    #M.starttls()
    M = imaplib.IMAP4_SSL(host)
    M.login(user, pw)
    return M

def stats(opts,config):
    M = login(opts,config)
    print("mailboxes:")
    (typ, res) = M.list()
    if typ!="OK":
        print("Cannot list mailboxes: {} {}".format(typ,res))
        exit(1)
    for _ in res:
        (flags, delimiter, mailbox_name) = parse_list_response(_)
        try:
            (t, r) = M.status(f'"{mailbox_name}"',"(MESSAGES RECENT UIDNEXT UIDVALIDITY UNSEEN)")
            r = r[0].decode('utf-8')
            if r[0]=='"':
                m = re.search('"(.*)" (.*)',r)
                flags = m.group(2)
            else:
                flags = r.split(" ",maxsplit=1)[1]
            print("{:20}: {}".format(mailbox_name,flags))
        except imaplib.IMAP4.error as e:
            r = e
    print("")
    print("Inbox:")
    M.select()
    (typ, res) = M.search(None, 'ALL')
    for num in res[0].split():
        (typ,data) = M.fetch(num,'(RFC822)')
        msg = email.message_from_bytes(data[0][1])
        print(msg.get('Date'),msg.get('Subject'))
        
        
import mailbox

def download(opts,config,mailbox_name):
    S = login(opts,config)
    S.select(mailbox_name)

    typ, res = S.search(None, 'ALL')
    if typ!="OK":
        print(res)
        exit(1)
    mbox_copy = mailbox.mbox(mailbox_name+".mbox")
    for num in res[0].split():
        ok, date = S.fetch(num, '(INTERNALDATE)')
        date2 = imaplib.Internaldate2tuple(date[0])
        ok, data = S.fetch(num, '(RFC822)')
        content = data[0][1]
        flags = data[1]
        flags2 = imaplib.ParseFlags(flags)
        msg = email.message_from_bytes(data[0][1])
        print("Message %s flags=%s %s / %s / %s " % (num,flags,msg.get('Message-Id').strip(),msg.get('Date'),msg.get('Subject')))
    S.close()
    S.logout()

if __name__ == "__main__":
    import argparse

    a = argparse.ArgumentParser()
    a.add_argument("--config", help="Specify config file", default="config.ini")
    a.add_argument("--stats", help="print stats about the IMAP directory", action="store_true")
    a.add_argument("--download", help="Download a mailbox")
    opts = a.parse_args()


    import configparser
    config = configparser.ConfigParser()
    config.read(opts.config)


    if opts.stats:
        stats(opts,config)

    if opts.download:
        download(opts,config,opts.download)
