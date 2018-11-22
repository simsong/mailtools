#!/usr/bin/env python3

"""
Extract all addresses from MacOS addressbook
"""

import sqlite3
import os
import time
import sys
import glob
from collections import defaultdict
from subprocess import Popen,PIPE

AB_DIR          = os.path.join(os.environ['HOME'], 'Library/Application Support/AddressBook')

DEFAULT_DBFILE = os.path.join(AB_DIR,"AddressBook-v22.abcddb")
IGNORE_DOMAINS = ".mil,.gov"


def extract(fname):
    if not os.path.exists(fname):
        raise FileNotFoundError(fname)

    ignore = set(args.ignore.split(","))

    conn = sqlite3.connect(fname)
    c = conn.cursor()
    c.execute("select ZFIRSTNAME,ZLASTNAME,ZADDRESS,ZABCDEMAILADDRESS.ZOWNER from ZABCDRECORD,ZABCDEMAILADDRESS where ZABCDRECORD.Z_PK = ZABCDEMAILADDRESS.ZOWNER")

    for(f,l,e,id) in c.fetchall():
        if any( e.endswith(ign) for ign in ignore): 
            continue
        if f==None and l==None:
            continue
        yield (f,l),e

def best_email(emails):
    # Simple rules-based approach for finding the best email
    for email in emails:
        if "gmail" in email:
            return email
    for email in emails:
        if ".edu" in email:
            return email
    shortest = min( len(email) for email in emails)
    for email in emails:
        if len(email) == shortest:
            return email

if __name__=="__main__":
    import argparse
    a = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                description="Extract email addresses from Apple Addressbook")
    a.add_argument("--dbfile",  help="Filename with database file", default=DEFAULT_DBFILE)
    a.add_argument("--debug",   help="debug", action="store_true")
    a.add_argument("--ignore",  help="specify a comma-separated list of domains to ignore", default=IGNORE_DOMAINS)
    a.add_argument("--all",     help="All addressbooks", action='store_true')
    a.add_argument("inputs",    nargs="*")
    args = a.parse_args()

    if args.all:
        path = os.path.join(AB_DIR,"Sources/*/AddressBook-v22.abcddb")
        dbfiles = [DEFAULT_DBFILE] + glob.glob(path)
    else:
        dbfiles = [args.dbfile]        

    # For each (f,l) and e, record the email address
    names = defaultdict(list)
    for fname in dbfiles:
        print("fname:",fname)
        for key,email in extract(fname):
            names[key].append(email)
    print(f"Extracted {len(names)} names")
    sent_emails = set()
    for (key,l) in names.items():
        best = best_email(l)
        if best in sent_emails:
            continue
        sent_emails.add(best)
        print(key[0],key[1],best)
