#!/usr/bin/python
#
# Scan all of my mail for mail that matches a regular expression. This was used to prepare evidence.

import os
import re
import csv
import sets

home = os.getenv("HOME")

dirs  = [home + "/arch/OldMail"]
search_re = re.compile("(simson|beth|charlie)",re.I)

privledged_re = re.compile("(marvin|marian)")

output_dir = home + "/discovery/email/"
output_dir_reg = output_dir + "reg/"
output_dir_priv = output_dir + "priv/"

rmail_divider = "\x1f\x0c"
report = csv.writer(open("report.csv","wb"))
preport = csv.writer(open("preport.csv","wb"))
head = ['snum','query','to','cc','from','subject','date','message-id','lines','original file']
report.writerow(head)
preport.writerow(head)

snumber = 1
processed = 0;

seen_messageIDs = sets.Set()


def privledged(msg):
    """Returns True if the message is privledged"""
    for f in ['To','From','Cc']:
        try:
            if privledged_re.search(msg[f]): return True
        except TypeError:
            pass
    return False

def save_message(msg,path):
    """Saves msg in path. Increments snumber """
    global snumber
    fn = "%s/s%06d.eml" % (path,snumber)
    if os.path.exists(fn):
        raise IOError,fn+": path already exists"
    f = open(fn,"w")
    f.write(str(msg))
    f.close()
    snumber += 1
    

def process_buffer(fn,buf):
    global snumber,processed
    processed += 1
    def strfix(m):
        if m==None: return ""
        if len(m)>30: return m[0:30]+"..."
        return m
    import email,sys
    m = search_re.search(buf)
    if m:
        what_matched = m.group(0)
        msg = email.message_from_string(buf)
        to = strfix(msg['To'])
        cc = strfix(msg['Cc'])
        messageid = msg['Message-ID']
        lines = len(buf.split("\n"))
        rept = [snumber,what_matched,to,cc,msg['From'],msg['Subject'],msg['Date'],msg['Message-ID'],lines,fn]

        if messageid and len(messageid)>6 and messageid in seen_messageIDs:
            return
        seen_messageIDs.add(messageid)

        if privledged(msg):
            preport.writerow(rept)
            save_message(msg,output_dir_priv)
        else:
            report.writerow(rept)
            save_message(msg,output_dir_reg)
     
    sys.stdout.write("Total processed: %8d  Total kept: %8d\r" % (processed,snumber))
    sys.stdout.flush()

def process_file(fn):
    import mailbox
    msg = open(fn,"r").read()
    if rmail_divider in msg:
        msgs = msg.split(rmail_divider)
        for m in msgs[1:]:
            pos = m.find("\n",2)
            process_buffer(fn,m[pos+1:])
        return 
    for msg in mailbox.mbox(fn,create=False):
        process_buffer(fn,str(msg))

if(__name__=="__main__"):
    for d in dirs:
        for (dirpath, dirnames, filenames) in os.walk(d):
            for f in filenames:
                fn = dirpath + "/" + f
                if fn.endswith(".pdf"): continue
                process_file(fn)
    print 
