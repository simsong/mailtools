#!/usr/bin/env python36

import re
import sys
import os

name_value_re = re.compile("([a-zA-Z ]+): *(.*)")

def process(config,f):
    d = {}
    for line in f:
        m = name_value_re.search(line)
        if m:
            d[m.group(1).lower()] = m.group(2)
    with open(config['DEFAULT']['csv_file'],'a') as f:
        if f.tell()==0:
            # print the headers
            print("\t".join(cols),file=f)
        print("\t".join([d.get(col.lower(),"") for col in cols]),file=f)
        


if __name__=="__main__":
    import argparse

    a = argparse.ArgumentParser()
    a.add_argument("--config", help="config file with private data")
    a.add_argument("inputs", nargs="+")
    opts = a.parse_args()

    if opts.config:
        import configparser
        config = configparser.ConfigParser()
        config.read(opts.config)
        
        from_addr = config['DEFAULT']['from']
        csv_file  = config['DEFAULT']['csv_file']
        cols      = config['DEFAULT']['keep_cols'].replace(" ","").split(",")
    else:
        raise RuntimeError("--config must be specified")


    for fn in opts.inputs:
        if os.path.isfile(fn):
            process(config,open(fn))
        if os.path.isdir(fn):
            for fname in os.listdir(fn):
                process(config,open(os.path.join(fn,fname)))
