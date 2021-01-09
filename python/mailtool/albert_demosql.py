"""albert_demo1.py:
 
Demonstrates a AlbertProcessor.

This processor gets called for every email message in a path.  It
includes a Command Line Interface (CLI). The CLI will be moved into
another program later.

"""


import os
import re
import csv
import logging
import mailbox
import sys
import pandas as pd
from datetime import datetime
from collections import defaultdict
import calendar
import pandas as pd
import matplotlib as mpl
import matplotlib.cm as cm
import numpy as np
import matplotlib.pyplot as plt

assert sys.version>'3.0.0'

from albert.AbstractAlbertProcessor import AbstractAlbertProcessor
from albert.Albert import Albert
from albert.SQLDatabaseLoader import SQLDatabaseLoader

"""
Here is the initial albert cli.
It creates an Albert extractor with a SQLMailStats as a callback,
then it asks the SQLMailStats to print a report.
"""

if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Demo program that uses albert to scan a mailbox and print stats',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("path", nargs="*", help="Files or Directories to scan")
    args = parser.parse_args()

    # Load the SQL database
    sdl  = SQLDatabaseLoader()
    alb = Albert(sdl)  # get a scanner with the specified callback
    for p in args.path:
        alb.scan(p)             # scan
    sdl.commit()                # commit the database
