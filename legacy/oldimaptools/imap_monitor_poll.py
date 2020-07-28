# This version does the monitoring with poll, since imaplib2 seems a bit flakey
# Not sure that it works well either.

import time, os
from threading import *
 
meuser = "simsong"
mepass = open( os.getenv("HOME")+"/.me").read().strip()

seen_messageids = set()


def copy_new(M,archive_box):
    """Scan for new mail and copy it"""
    import email
    r, data = M.search(None,'(NOT DELETED)')
    print "copy_new; r=",r,"len(data)=",len(data)
    if r!="OK":
        return
    # Get the MessageID for each
    for num in data[0].split():
        typ, msg_data = M.fetch(num, '(FLAGS BODY.PEEK[HEADER])')
        if r'\Deleted' in msg_data[0][0]:
            continue        # ignore deleted messages
        msg = email.message_from_string(msg_data[0][1])
        mid = msg.get('message-id','')
        if mid in seen_messageids:
            continue        # already processed
        seen_messageids.add(mid)
        subject = msg.get('subject','')
        print "Received ",mid,subject
        M.copy(num,archive_box)


if __name__=="__main__":
    import slgimap,imaplib
    M = slgimap.connection(imaplib)
    M.select("INBOX") # We need to get out of the AUTH state, so we just select the INBOX.
    print dir(M)

    archive_box = slgimap.archive_mbox(M)
    while True:
        copy_new(M,archive_box)
        time.sleep(5)
        
