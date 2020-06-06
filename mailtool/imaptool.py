#!/usr/bin/python

import getpass
import email
import re
import mailbox
import configparser
import logging
from abc import ABC,abstractmethod

try:
    import imapclient
    import imapclient.exceptions
except ImportError as e:
    print("Please install imapclient with 'pip install imapclient' or 'conda install imapclient'",file=sys.stderr)
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
                                description="IMAP mail copy program")
    parser.add_argument("--config", help="Specify config file where IMAP information is held.", default="config.ini")
    parser.add_argument("--debug",  help="Enable debugging", action='store_true')
    parser.add_argument("--list_folders", help="list all of the folders on the server", action='store_true')
    parser.add_argument("--status_folders", help="Print status information about each folder", action='store_true')

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



    
