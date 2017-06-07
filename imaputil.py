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


def stats(opts,config):
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
    (typ, res) = M.list()
    if typ!="OK":
        print("Cannot list mailboxes: {} {}".format(typ,res))
        exit(1)
    print("mailboxes:")
    for _ in res:
        (flags, delimiter, mailbox_name) = parse_list_response(_)
        try:
            status = M.status(f'"{mailbox_name}"',"(MESSAGES RECENT UIDNEXT UIDVALIDITY UNSEEN)")
        except imaplib.IMAP4.error as e:
            status = e
        print("{:20}: {}".format(mailbox_name,status))
    print("Inbox:")
    M.select()
    (typ, res) = M.search(None, 'ALL')
    for num in res[0].split():
        (typ,data) = M.fetch(num,'(RFC822)')
        msg = email.message_from_bytes(data[0][1])
        print(msg.get('Date'),msg.get('Subject'))
        
        

def mailcopy(u,p):
    S = imaplib.IMAP4('192.168.1.2')
    # S.login(u,p)
    S.login_cram_md5(u,p)
    S.select()

    D = imaplib.IMAP4('localhost')
    D.login_cram_md5(u,p)
    D.select()

    typ, res = S.search(None, 'ALL')
    print("typ='%s'" % typ)
    #print "res=",res
    for num in res[0].split():
        ok, date = S.fetch(num, '(INTERNALDATE)')
        date2 = imaplib.Internaldate2tuple(date[0])
        ok, data = S.fetch(num, '(RFC822)')
        content = data[0][1]
        flags = data[1]
        flags2 = imaplib.ParseFlags(flags)
        msg = email.message_from_string(data[0][1])
        print("Message %s flags=%s %s / %s " % (num,flags,msg.get('Date'),msg.get('Subject')))
        D.append(None,flags2,date2,content) # #2 is the flags
    S.close()
    S.logout()
    D.close()
    D.logout()

if __name__ == "__main__":
    import argparse

    a = argparse.ArgumentParser()
    a.add_argument("--config", help="Specify config file", default="config.ini")
    a.add_argument("--stats", help="print stats about the IMAP directory", action="store_true")
    opts = a.parse_args()


    import configparser
    config = configparser.ConfigParser()
    config.read(opts.config)


    if opts.stats:
        stats(opts,config)
