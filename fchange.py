#!/usr/bin/env python3
# coding=UTF-8
#
# File change detector

__version__='0.0.1'
import os.path,sys

import os,sys,re,collections,sqlite3
import datetime

# Replace this with an ORM?
schema = \
"""
PRAGMA cache_size = 200000;
CREATE TABLE IF NOT EXISTS files (fileid INTEGER PRIMARY KEY,
                                  pathid INTEGER NOT NULL,
                                  mtime TIMET NOT NULL, 
                                  size INTEGER NOT NULL, 
                                  hashid INTEGER NOT NULL, 
                                  scanid INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS files_idx0 ON files(fileid);
CREATE INDEX IF NOT EXISTS files_idx1 ON files(pathid);
CREATE INDEX IF NOT EXISTS files_idx2 ON files(mtime);
CREATE INDEX IF NOT EXISTS files_idx3 ON files(size);
CREATE INDEX IF NOT EXISTS files_idx4 ON files(hashid);
CREATE INDEX IF NOT EXISTS files_idx5 ON files(scanid);

CREATE TABLE IF NOT EXISTS paths (pathid INTEGER PRIMARY KEY,path TEXT NOT NULL UNIQUE);
CREATE INDEX IF NOT EXISTS paths_idx1 ON paths(pathid);
CREATE INDEX IF NOT EXISTS paths_idx2 ON paths(path);

CREATE TABLE IF NOT EXISTS hashes (hashid INTEGER PRIMARY KEY,hash TEXT NOT NULL UNIQUE);
CREATE INDEX IF NOT EXISTS hashes_idx1 ON hashes(hashid);
CREATE INDEX IF NOT EXISTS hashes_idx2 ON hashes(hash);

CREATE TABLE IF NOT EXISTS scans (scanid INTEGER PRIMARY KEY,time DATETIME NOT NULL UNIQUE);
CREATE INDEX IF NOT EXISTS scans_idx1 ON scans(scanid);
CREATE INDEX IF NOT EXISTS scans_idx2 ON scans(time);

"""

"""Explaination of tables:
files         - list of all files
hashes       - table of all hash code
"""

def create_schema(conn):
    # If the schema doesn't exist, create it
    c = conn.cursor()
    for line in schema.split(";"):
        print(line,end="")
        c.execute(line)

def iso_now():
    return datetime.datetime.now().isoformat()[0:19]

def hash_file(path):
    from hashlib import md5
    m = md5()
    with open(path,"rb") as f:
        while True:
            buf = f.read(65535)
            if buf:
                m.update(buf)
            else:
                break
    return m.hexdigest()
        

class Scanner(object):
    def __init__(self,db):
        self.conn = sqlite3.connect(args.db)
        c = self.conn.cursor()

    def get_hashid(self,hash):
        self.c.execute("INSERT or IGNORE INTO hashes (hash) VALUES (?);",(hash,))
        self.c.execute("SELECT hashid from hashes where hash=?",(hash,))
        return self.c.fetchone()[0]

    def get_scanid(self,now):
        self.c.execute("INSERT or IGNORE INTO scans (time) VALUES (?);",(now,))
        self.c.execute("SELECT scanid from scans where time=?",(now,))
        return self.c.fetchone()[0]

    def get_pathid(self,path):
        self.c.execute("INSERT or IGNORE INTO paths (path) VALUES (?);",(path,))
        self.c.execute("SELECT pathid from paths where path=?",(path,))
        return self.c.fetchone()[0]

    def process_path(self,scanid,path):
        """ Add the file to the database database. If it is there and the mtime hasn't been changed, don't re-hash."""

        try:
            st = os.stat(path)
        except FileNotFoundError as e:
            return 
        pathid = self.get_pathid(path)
        
        # See if this file with this length is in the databsae
        self.c.execute("SELECT hashid from files where pathid=? and mtime=? and size=? LIMIT 1",(pathid,st.st_mtime,st.st_size))
        row = self.c.fetchone()
        try:
            if row:
                (hashid,) = row
            else:
                hashid = self.get_hashid(hash_file(path))
            self.c.execute("INSERT into files (pathid,mtime,size,hashid,scanid) values (?,?,?,?,?)",
                           (pathid,st.st_mtime,st.st_size,hashid,scanid))
        except PermissionError as e:
            pass
        except OSError as e:
            pass
        except FileNotFoundError as e:
            pass

    def ingest(self,root):
        import time

        self.c = self.conn.cursor()
        self.c.execute("BEGIN TRANSACTION")

        scanid = self.get_scanid(iso_now())

        count = 0
        for (dirpath, dirnames, filenames) in os.walk(root):
            print(dirpath,end='')
            for filename in filenames:
                self.process_path(scanid,os.path.join(dirpath,filename))
            print("   {}".format(len(filenames)))
            count += len(filenames)
            self.conn.commit()

        self.conn.commit()
        print("Total files added to database: {}".format(count))

def dump(conn,what):
    c = conn.cursor()
    for (scanid,time) in c.execute("select scanid,time from scans"):
        print(scanid,time)

def execselect(conn,sql,vals):
    c= conn.cursor()
    c.execute(sql,vals)
    return c.fetchone()


def report(conn,a,b):
    atime = execselect(conn,"select time from scans where scanid=?",(a,))[0]
    btime = execselect(conn,"select time from scans where scanid=?",(b,))[0]
    print("Report from {}->{}".format(atime,btime))
    print("New files:")
    print("Deleted files:")
    print("Changed files:")
    print("Renamed files:")
    print("Duplicate files:")
    c = conn.cursor()
    d = conn.cursor()
    c.execute("select hashid,ct from (select hashid ,count(*) as ct from files where scanid=? group by hashid) natural join hashes where ct>1;",(b,))
    for (hashid,ct) in c:
        d.execute("SELECT path FROM files NATURAL JOIN paths WHERE scanid=? and hashid=?",(b,hashid,))
        for (path) in d:
            print(path)
        print("-----------")
        

if(__name__=="__main__"):
    import argparse
    parser = argparse.ArgumentParser(description='Compute file changes',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('roots', type=str, nargs='*', help='Directories to process')
    parser.add_argument("--debug",action="store_true")
    parser.add_argument("--create",action="store_true",help="Create database")
    parser.add_argument("--db",help="Specify database location",default="data.sqlite3")
    parser.add_argument("--dump",help="[scans]")
    parser.add_argument("--report",default="1-2",help="Report what's changed between 1 and 2")

    args = parser.parse_args()

    if args.create:
        try:
            os.unlink(args.db)
        except FileNotFoundError:
            pass
        conn = sqlite3.connect(args.db)
        create_schema(conn)

    if args.dump:
        dump(sqlite3.connect(args.db),args.dump)
        exit(0)

    if args.report:
        m = re.search("(\d+)-(\d+)",args.report)
        if not m:
            print("Usage: --report N-M")
            exit(1)
        report(sqlite3.connect(args.db),int(m.group(1)),int(m.group(2)))

    s = Scanner(args.db)

    if args.roots:
        for root in args.roots:
            print(root)
            s.ingest(root)

