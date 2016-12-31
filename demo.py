#!/usr/bin/env python3.5
# coding=UTF-8
#
# Initial thoughts on a mail analysis tool.

__version__='0.0.1'

import sqlite3
import os,sys,time

if sys.version_info < (3,4): raise RuntimeError("Requires Python 3.2 or above")

fn = os.path.join(os.getenv("HOME"),"Library/Mail/V4/MailData/Envelope Index")
conn = sqlite3.connect(fn)


def t(x):
    return time.asctime(time.localtime(x))

def sqlv(c,s):
    c.execute(s)
    return c.fetchone()[0]

def get_addresses(email):
    c = conn.cursor()
    addresses = set()
    for (rowid,address,comment) in c.execute("select rowid,address,comment from addresses where address like ?",(email,)):
        print(rowid,address,comment)
        addresses.add(rowid)
    return addresses

if __name__=="__main__":
    import argparse

    a = argparse.ArgumentParser()
    a.add_argument("--sender")
    opts = a.parse_args()
    if opts.sender:
        ids = get_addresses(opts.sender)
        print("There are {} addresses for {}".format(len(ids),opts.sender))
        exit(0)


    c = conn.cursor()
    print("Total messages: {:0,}".format(sqlv(c,"select count(*) from messages")))
    c.execute("select m.date_sent,m.subject_prefix,s.subject,s.normalized_subject "
              "from messages as m left join subjects as s where m.subject=s.rowid order by date_sent limit 100")
    for (date_sent,subject_prefix,subject,normalized_subject) in c:
        if subject!=normalized_subject:
            print(t(date_sent),subject_prefix,"subject=",subject,"normalized_subject=",normalized_subject)

