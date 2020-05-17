#!/usr/bin/python

import getpass
import imaplib
imaplib._MAXLINE = 10000000
import email
import re
import mailbox


list_response_pattern = re.compile(
    r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)'
)


def parse_list_response(line):
    match = list_response_pattern.match(line.decode('utf-8'))
    flags, delimiter, mailbox_name = match.groups()
    mailbox_name = mailbox_name.strip('"')
    return (flags, delimiter, mailbox_name)


def login(args,config):
    host = config["imap"]["server"]
    user = config["imap"]["username"]
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

def recursive_explore(args, config):
    M = login(args,config)
    print("mailboxes:")
    (typ, res) = M.list()
    if typ!="OK":
        print("Cannot list mailboxes: {} {}".format(typ,res))
        exit(1)

    print("RES:",res)
    for _ in res:
        (flags, delimiter, mailbox_name) = parse_list_response( _ )
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

    if args.dups:
        seen = set()
        seen_count = 0
        for mailbox_name in ['[Gmail]/Sent Mail']:
            M.select(f'"{mailbox_name}"') # must transmit double-quotes!
            res, data = M.uid('search', None, "ALL") # searches all email and returns uids
            if res=="OK":
                messages = data[0].split()
                print("Total Messages: ",len(messages))
                for (ct,num) in enumerate(messages):
                    result, data = M.uid('fetch', num, '(BODY.PEEK[HEADER])')
                    if result=='OK':
                        email_header = email.message_from_bytes(data[0][1])
                        print(ct,num,email_header['Date'], email_header['From'], email_header['message-id'])
                        if email_header['message-id'] in seen:
                            seen_count += 1
                            print(f"*** PREVIOUSLY SEEN ***  count={seen_count}")
                        seen.add( email_header['message-id'] )
        print("Seen count: ",seen_count)

    """
    print("Inbox:")
    M.select()
    (typ, res) = M.search(None, 'ALL')
    for num in res[0].split():
        (typ,data) = M.fetch(num,'(RFC822)')
        msg = email.message_from_bytes(data[0][1])
        print(msg.get('Date'),msg.get('Subject'))
    """
        
        
def download(args,config,mailbox_name):
    M = login(args,config)
    M.select(mailbox_name)

    typ, res = M.search(None, 'ALL')
    if typ!="OK":
        print(res)
        exit(1)
    mbox_copy = mailbox.mbox(mailbox_name+".mbox")
    for num in res[0].split():
        ok, date = M.fetch(num, '(INTERNALDATE)')
        date2 = imaplib.Internaldate2tuple(date[0])
        ok, data = M.fetch(num, '(RFC822)')
        content = data[0][1]
        flags = data[1]
        flags2 = imaplib.ParseFlags(flags)
        msg = email.message_from_bytes(data[0][1])
        print("Message %s flags=%s %s / %s / %s " % (num,flags,msg.get('Message-Id').strip(),msg.get('Date'),msg.get('Subject')))
    M.close()
    M.logout()

if __name__ == "__main__":
    import argparse

    a = argparse.ArgumentParser()
    a.add_argument("--config", help="Specify config file", default="config.ini")
    a.add_argument("--stats", help="print stats about the IMAP directory", action="store_true")
    a.add_argument("--download", help="Download a mailbox")
    a.add_argument("--dups", help="Find dups", action='store_true')
    args = a.parse_args()


    import configparser
    config = configparser.ConfigParser()
    config.read(args.config)


    if args.stats or args.dups:
        recursive_explore(args, config)

    if args.download:
        download(args,config,args.download)
