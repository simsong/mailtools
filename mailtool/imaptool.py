#!/usr/bin/python

import getpass
import email
import re
import mailbox
import configparser
import logging
from abc import ABC,abstractmethod

HELP="""
This program is a tool for learning about IMAP and for performing simple actions. 
By design, IMAP clients are supposed to maintain a local copy of the server's mailbox and 
only download updates. Each message in the imap mailbox has a sequence number (0..max messages)
and a UID (unique identifier; doesn't change). 

This program uses imapclient, which is an easier-to-use IMAP client than the one that
comes with the Python standard library. However, the client does not maintain the client-side cache.
We may develop a version of imapclient that does maintain a client-side cache and performs synchronization.
"""

"""
fetch(['UID','ENVELOPE']) returns an object that looks like this:
332074 {b'SEQ': 172, 
        b'ENVELOPE': Envelope(date=datetime.datetime(2020, 6, 6, 18, 9, 58), 
                     subject=b'Re: need to reschedule', 
                     from_=(Address(name=b'Nosmis Noel', route=None, mailbox=b'nosmis', host=b'gmail.com'),), 
                     sender=(Address(name=b'Nosmis Noel', route=None, mailbox=b'nosmis', host=b'gmail.com'),), 
                     reply_to=(Address(name=b'Nosmis Noel', route=None, mailbox=b'nosmis', host=b'gmail.com'),), 
                     to=(Address(name=b'Simson Garfinkel', route=None, mailbox=b'simsong', host=b'gmail.com'),), 
                     cc=None, 
                     bcc=None, 
                     in_reply_to=b'<0315F6E8-CDFF-49D7-AB8D-29CA8983D0D6@gmail.com>', 
                     message_id=b'<CA+xaqTniOnN3GmOy6L2o=F-R2pyKR2w-Z0sDxhTXnf15ZYR7ww@mail.gmail.com>')}
"""

try:
    import imapclient
    import imapclient.exceptions
except ImportError as e:
    print("Please install imapclient with 'pip install imapclient' or 'conda install imapclient'",file=sys.stderr)
    print("Documentation is at https://imapclient.readthedocs.io/en/2.1.0/",file=sys.stderr)
    exit(1)

def imap_login(config, debug=None):
    """Log in to an IMAP server using config information stored in a config file.
    If the password is not provided, ask the user.
    return the imap connection
    """
    try:
        host = config["imap"]["server"]
        user = config["imap"]["username"]
    except KeyError as k:
        logging.error("config file must contain server and username options in the [imap] section")
        exit(1)

    if debug:
        print(f"host: {host}  user: {host}", file=sys.stderr)

    try:
        pw = config["imap"]["password"]
    except KeyError:
        pw = getpass.getpass(f"Login for {user}@{host}: ")

    server = imapclient.IMAPClient(host, use_uid=True)
    server.login(user, pw)
    return server


##
## We currently implement mailbox actions as subclasses of an abstract base class.

class AbstractMailboxAction(ABC):
    def setM(self, M):
        self.M = M

    @abstractmethod
    def process_mailbox(self, mailbox):
        pass
    
class Mailbox_Stats(AbstractMailboxAction):
    def process_mailbox(self , mailbox):
        print(mailbox)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                description=HELP)
    parser.add_argument("--config", help="Specify config file where IMAP information is held.", default="config.ini")
    parser.add_argument("--debug",  help="Enable debugging", action='store_true')
    parser.add_argument("--list_folders", help="list all of the folders on the server", action='store_true')
    parser.add_argument("--status_folders", help="Print status information about each folder", action='store_true')
    parser.add_argument("--list",  help="List messages in a specified mailbox. Specify INBOX for inbox")

    args = parser.parse_args()

    # Get the config and use that to log in and get an imap connection
    config = configparser.ConfigParser()
    config.read(args.config)
    server = imap_login(config)

    if args.list_folders:
        for (flags, delimiter, name) in server.list_folders():
            print(name)

    if args.status_folders:
        for (flags, delimiter, name) in server.list_folders():
            try:
                status = server.folder_status(name)
                print(f"{name:20s} {status}")
            except imapclient.exceptions.IMAPClientError as e:
                print(e)

    if args.list:
        select_info = server.select_folder(args.list)
        messages = server.search(['ALL']) # get all messages
        for msgid, data in server.fetch(messages,['UID','ENVELOPE']).items():
            envelope = data[b'ENVELOPE']
            print(f"{msgid} {envelope.from_[0]} {envelope.date}")

    
                
