import os
import re
import csv
import logging
import mailbox
import sys

import email
import email.utils

from collections import defaultdict

assert sys.version>'3.0.0'

from albert.AbstractAlbertProcessor import AbstractAlbertProcessor
from albert.Albert import Albert


class SimpleMailGrapher(AbstractAlbertProcessor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.flows  = defaultdict(int)

    def process_message(self,msg):
        for from_ in msg.get_all('from',[]):
            (from_realname, from_email) = email.utils.parseaddr(from_)

            for to_ in msg.get_all('to',[]) + msg.get_all('cc',[]):
                (to_realname, to_email) = email.utils.parseaddr(to_)
                self.flows[ (from_email,to_email) ] += 1

    def report(self):
        print("digraph G {")
        for (pair,count) in self.flows.items():
            print(f'"{pair[0]}" -> "{pair[1]}" [label="{count}",fontsize=24];')
        print("}")

        
if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Demo program that uses albert to scan a mailbox and print stats',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("path", nargs="*", help="Files or Directories to scan")
    args = parser.parse_args()
    smg  = SimpleMailGrapher()

    # Get a scanner

    alb = Albert(smg)  # get a scanner with the specified callback
    for p in args.path:
        alb.scan(p)             # scan

    smg.report()
