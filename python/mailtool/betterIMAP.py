#
# We may want to abandon this and moave to imapclient

imaplib._MAXLINE = 10000000

class BetterIMAPConnection:
    """Our class for working with IMAP"""
    
    def __init__(self, debug=False):
        self.debug = debug

    ##
    ## Some helper functions
    ##
    LIST_RESPONSE_PATTERN = re.compile(
        r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)'
    )
    def mailboxes(self):
        """Return all the mailboxes."""

        # It is surprising that this functionality is not built in to the IMAP class
        def parse_list_response(line):
            match = self.LIST_RESPONSE_PATTERN.match(line.decode('utf-8'))
            flags, delimiter, mailbox_name = match.groups()
            mailbox_name = mailbox_name.strip('"')
            return (flags, delimiter, mailbox_name)

        (typ, res) = self.M.list()
        if typ!="OK":
            logging.error("Cannot list mailboxes: {} {}".format(typ,res))
            raise RuntimeError("Cannot list mailboxes")
        for _ in res:
            (flags, delimiter, mailbox_name) = parse_list_response( _ )
            yield mailbox_name

    def process_all_mailboxes(self,obj):
        """Call obj.process_mailbox(self,M) for each mailbox"""

    def select(self, mailbox_name):
        """Select the mailbox. Works with spaces in the name (unlike normal IMAP select)"""
        self.M.select(f'"{mailbox_name}"') # mailbox name must be sent in double-quotes
        return self.M
        
    def mailbox_flags(self, mailbox_name):
        """Return the flags for the mailbox in a python-friendly manner."""

