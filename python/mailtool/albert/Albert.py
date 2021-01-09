import os
import logging
import mailbox


class Albert:
    def __init__(self, callback):
        self.callback = callback

    def process_mailbox(self, M):
        for message in M:
            self.callback.process_message(message)

    def process_file(self, filename):
        if filename.endswith(".mbox"):
            mails = mailbox.mbox( filename )
            self.process_mailbox(mails)
        else:
            logging.error("Don't know how to process "+filename)

    def scan_directory(self, dirname):
        """Right now we hard-code mbox"""
        logging.info("scan_directory(%s)",dirname)
        for (dirpath, dirnames, filenames) in os.walk(dirname):
            for fname in filenames:
                self.process_file( os.path.join(dirpath, fname))

    def scan(self, name):
        if os.path.isdir(name):
            self.scan_directory(name)
        else:
            self.process_file(name)



