#!/usr/bin/env python3.5
# coding=UTF-8
#
# Initial thoughts on a mail analysis tool.

__version__ = '0.0.1'

import sqlite3
import os, sys, time

if sys.version_info < (3, 4): raise RuntimeError("Requires Python 3.4 or above")

appleMailDB = os.path.join(os.getenv("HOME"), "Library/Mail/V4/MailData/Envelope Index")
conn = sqlite3.connect(appleMailDB)


def t(x):
    return time.asctime(time.localtime(x))


def sqlv(c, s):
    c.execute(s)
    return c.fetchone()[0]


def report_sender(address, ids_and_names):
    # Compute the count for each message sent by each ID
    ids = [str(a[0]) for a in ids_and_names]
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
    for (id, name) in ids_and_names:
        if name:
            print("     {}  ({} / {})".format(name,
                                              sent_count.get(id,""),
                                              recv_count.get(id,"")))
    print("")


def report_senders(email):
    from collections import defaultdict
    addresses = defaultdict(list)
    c = conn.cursor()
    for (rowid, address, comment) \
            in c.execute("SELECT rowid,address,comment FROM addresses WHERE address LIKE ? ORDER BY address", (email,)):
        addresses[address].append((rowid, comment))
    for address in addresses:
        report_sender(address, addresses[address])
    print("Total email addresses: {}".format(len(addresses)))


if __name__ == "__main__":
    import argparse

    a = argparse.ArgumentParser()
    a.add_argument("--db", help="Specifies input database", default=appleMailDB)
    a.add_argument("--search", help="Search for information about SEARCH")
    a.add_argument("--sender", help="Information about SENDER; SENDER can be a partial email address")
    a.add_argument("--senders", help="Report on all senders", action="store_true")
    opts = a.parse_args()
    if opts.search:
        search_addresses(opts.sender)
        exit(0)
    if opts.sender or opts.senders:
        if opts.sender:  report_senders(opts.sender)
        if opts.senders: report_senders("")
        exit(0)

    c = conn.cursor()
    print("Total messages: {:0,}".format(sqlv(c, "select count(*) from messages")))
    c.execute("SELECT m.date_sent,m.subject_prefix,s.subject,s.normalized_subject "
              "FROM messages AS m LEFT JOIN subjects AS s WHERE m.subject=s.rowid ORDER BY date_sent LIMIT 100")
    for (date_sent, subject_prefix, subject, normalized_subject) in c:
        if subject != normalized_subject:
            print(t(date_sent), subject_prefix, "subject=", subject, "normalized_subject=", normalized_subject)
