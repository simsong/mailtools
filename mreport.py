#!/usr/bin/env python3.5
# coding=UTF-8
#
# Initial thoughts on a mail analysis tool.

__version__ = '0.0.1'

import sqlite3
import os, sys, time
import datetime
import dateutil

if sys.version_info < (3, 4): raise RuntimeError("Requires Python 3.4 or above")

meDefault = os.environ["USER"] + "@"
appleMailDB = "Envelope Index"
conn = sqlite3.connect(appleMailDB,uri=True)


def sqlv(c, s):
    c.execute(s)
    return c.fetchone()[0]


class Email:
    """Represents an email address"""
    __slots__ = ['id','address','comment']
    def __init__(self,id,address,comment):
        self.id = id
        self.address = address
        self.comment = comment
    def idstr(self):
        return str(self.id)



def getSenderIDs(email):
    print("email=",email)
    c = conn.cursor()
    for (rowid, address, comment) \
            in c.execute("SELECT rowid,address,comment FROM addresses WHERE address LIKE ? ORDER BY address",
                         (email+"%",)):
        yield Email(rowid, address, comment)

def sqlIdsForEmail(email):
    print(email)
    return ",".join([str(e.id) for e in getSenderIDs(email)])

def search_addresses(email):
    addresses = set()
    for e in getSenderIDs(email):
        addresses.add(e)

def report_sender(address, emails):
    # Compute the count for each message sent by each ID
    ids = [e.idstr() for e in emails]
    id_list = "(" + ",".join(ids) + ")"
    c = conn.cursor()

    # Tabulate the count of messages sent by each SENDER ID
    sent_count = {}               # Will be a list of counts for each id
    for (id,count) in c.execute("SELECT sender,count(*) FROM messages WHERE sender in "+id_list+" GROUP BY sender"):
        sent_count[id] = count
    # Tabulate the count of messages received by each ADDRESS ID
    recv_count = {}
    for (id,count) in c.execute("SELECT address_id,count(*) FROM recipients where address_id in "+id_list+" GROUP BY address_id"):
        recv_count[id] = count

    print("{}   ({} / {}):".format(address,sum(sent_count.values()),sum(recv_count.values())))
    for (id, name) in emails:
        if name:
            print("     {}  ({} / {})".format(name,
                                              sent_count.get(id,""),
                                              recv_count.get(id,"")))
    print("")


def report_senders(email):
    from collections import defaultdict
    emails = defaultdict(list)
    c = conn.cursor()
    for e in getSenderIDs(email):
        emails[e.address].append(e)
    for address in emails:
        report_sender(address, emails[address])
    print("Total email addresses: {}".format(len(emails)))


def tdate(x):
    return datetime.datetime(*time.localtime(x)[:6]).date()


def report_daily_messages():
    c = conn.cursor()
    c.execute("SELECT m.date_sent,m.subject_prefix,s.subject,s.normalized_subject "
              "FROM messages AS m LEFT JOIN subjects AS s WHERE m.subject=s.rowid ORDER BY date_sent LIMIT 100")
    for (date_sent, subject_prefix, subject, normalized_subject) in c:
        if subject != normalized_subject:
            print(tdate(date_sent), subject_prefix, "subject=", subject, "normalized_subject=", normalized_subject)

def report_daily():
    """"For each day, report the date, the number of messages received, and the number of messages sent."""

    c = conn.cursor()
    cmd = "SELECT d,sum(total)-sum(sender),sum(sender) FROM (select date(date_sent,'unixepoch') as d, 1 as total, sender in ("+sqlIdsForEmail(opts.me)+") as sender from messages) GROUP BY d"
    c.execute(cmd)
    sent = dict()
    recv = dict()
    for (datestr,recv_count,sent_count) in c:
        date = datetime.datetime.strptime(datestr,"%Y-%m-%d")
        if sent_count:
            sent[date] = sent_count
        if recv_count:
            recv[date] = recv_count
    print("Messages Sent: {}  ({} days from {} to {})".format(sum(sent.values()),len(sent.keys()),min(sent.keys()),max(sent.keys())))
    print("Messages Recv: {}  ({} days from {} to {})".format(sum(recv.values()),len(recv.keys()),min(recv.keys()),max(recv.keys())))
    print("Days without both SENT and RECV:")
    from dateutil.rrule import rrule,DAILY
    for day in rrule(DAILY,dtstart=min(sent.keys())).between(min(sent.keys()),max(sent.keys())):
        if day not in sent or day not in recv:
            print("    {} {} {}".format(day.date(),"SENT" if day in sent else "    ",
                                     "RECV" if day in recv else "    "))





if __name__ == "__main__":
    import argparse

    a = argparse.ArgumentParser()
    a.add_argument("--me", help="Sepcifies your username", default=meDefault)
    a.add_argument("--db", help="Specifies input database", default=appleMailDB)
    a.add_argument("--search", help="Search for information about SEARCH")
    a.add_argument("--sender", help="Information about SENDER; SENDER can be a partial email address")
    a.add_argument("--senders", help="Report on all senders", action="store_true")
    a.add_argument("--daily", help="Report daily messages sent and received", action="store_true")
    opts = a.parse_args()
    print(opts.me)
    if opts.search:
        search_addresses(opts.sender)
        exit(0)
    if opts.sender or opts.senders:
        if opts.sender:  report_senders(opts.sender)
        if opts.senders: report_senders("")
        exit(0)

    if opts.daily:
        report_daily()
