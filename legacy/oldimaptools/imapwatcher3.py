# a new watcher

from ProcImap.ProcImap import AbstractProcImap
from ProcImap.ImapMailbox import ImapMailbox
from ProcImap.ImapServer import ImapServer

class ImapWatcher(AbstractProcImap):
    def preprocess(self,header):
        # 'header' is an ImapMessage, which is a mailbox.Message
        # adding .fullprocess attribute causes the mail message to be downloaded and
        # the fullprocess funciton below to be run
        #
        # header['subject'] is the subject
        header.source_mailbox.copy(header.uid,"Archive") 
        print "subject:",header['subject'],"copied to archive"
        print ""
        return header
    

    def fullprocess(self,message):
        """Only called if header.fullprocess=True"""
        return

if __name__=="__main__":
    from ProcImap import imaplib2
    from ProcImap.Utils import log
    import os
    password = open( os.getenv("HOME")+"/.me").read().strip()
    while True:
        try:
            s = ImapServer("mail.me.com","simsong",password)
            mbx = ImapMailbox(path=(s,"INBOX"))
            mbx.trash = 'Trash'                 # specify a trash box
            print "calling ImapWatcher"
            w = ImapWatcher(mbx)
            w.run()
        except:
            log("caught exception")
            pass
    
    
        

        
