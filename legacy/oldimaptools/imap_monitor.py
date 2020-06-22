# from http://blog.hokkertjes.nl/2009/03/11/python-imap-idle-with-imaplib2/

import time, os
from threading import *
 
meuser = "simsong"
mepass = open( os.getenv("HOME")+"/.me").read().strip()

seen_messageids = set()


# This is the threading object that does all the waiting on 
# the event
class Idler(object):
    def __init__(self, conn):
        self.thread = Thread(target=self.idle)
        self.M = conn
        self.event = Event()
        self.seen_uids = set()
 
    def start(self):
        self.thread.start()
 
    def stop(self):
        # This is a neat trick to make thread end. Took me a 
        # while to figure that one out!
        self.event.set()
 
    def join(self):
        self.thread.join()
 
    def copy_new(self):
        """Scan for new mail and copy it"""
        import email
        r, data = self.M.search(None,'RECENT')
        #r, data = self.M.search(None,'ALL')
        if r!="OK":
            return
        # Get the MessageID for each
        for num in data[0].split():
            typ, msg_data = self.M.fetch(num, '(FLAGS BODY.PEEK[HEADER])')
            if r'\Deleted' in msg_data[0][0]:
                continue        # ignore deleted messages
            msg = email.message_from_string(msg_data[0][1])
            mid = msg.get('message-id','')
            if mid in seen_messageids:
                continue        # already processed
            seen_messageids.add(mid)
            subject = msg.get('subject','')
            print "Received ",mid,subject
            self.M.copy(num,self.archive_box)
            # need to copy it now.

    def idle(self):
        # Starting an unending loop here
        while True:
            # This is part of the trick to make the loop stop 
            # when the stop() command is given
            if self.event.isSet():
                return
            self.needsync = False
            # A callback method that gets called when a new 
            # email arrives. Very basic, but that's good.
            def callback(args):
                if not self.event.isSet():
                    self.needsync = True
                    self.event.set()

            # Do the actual idle call. This returns immediately, since it's asynchronous.
            self.M.idle(callback=callback)

            # This waits until the event is set. The event is set by the callback, when the server 'answers' 
            # the idle call and the callback function gets called.
            self.event.wait()

            # Because the function sets the needsync variable, this helps escape the loop without doing 
            # anything if the stop() is called. Kinda neat solution.
            if self.needsync:
                self.event.clear()
                self.copy_new()
 
# r, d2 = self.M.fetch(num, '(UID BODY)')
# returns:    19 (UID 1137 BODY ("TEXT" "PLAIN" ("CHARSET" "us-ascii") NIL NIL "7BIT" 20 1))

# r, d2 = self.M.fetch(num, '(UID RFC822)')
# returns:     ('20 (UID 1138 RFC822 {8633}', 'Return-path:\...  (entire message) 

# Had to do this stuff in a try-finally, since some testing 
# went a little wrong.....
# Set the following two lines to your creds and server

if __name__=="__main__":
    import slgimap,imaplib2
    M = slgimap.connection(imaplib2)
    M.select("INBOX") # We need to get out of the AUTH state, so we just select the INBOX.

    idler = Idler(M)  # Start the Idler thread
    idler.archive_box = slgimap.archive_mbox(M)
    idler.start()
    try:
        time.sleep(2*365*60*60*24) # Sleep for a long time (2 years)...
    except KeyboardInterrupt:
        print "exiting"
        exit(0)
    
