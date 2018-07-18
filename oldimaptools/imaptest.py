#!/usr/bin/env python
#
import getpass,imaplib,readline,time

print("Username:")
u = input().strip()
p = getpass.getpass()

print("Will attempt to log in every minute forever...")
while True:
    M = imaplib.IMAP4_SSL("smtp.nps.edu")
    M.debug=4
    M.login(u,p)
    del M
    time.sleep(60)

