import getpass, imaplib,os, re, sys
import imaplib
import email

list_response_pattern = re.compile(r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)')


def remove_dups(c,mbx):
    total_deleted = 0
    seen_messageids = set()
    r = c.select(mbx)
    if r[0]!='OK':
        print "ERROR: mbx=%s error=%s" % (mbx,r[1])
        return
    typ, data = c.search(None, 'ALL')
    try:
        messages = data[0].split()
        messages.reverse()
        for num in messages:
            #typ, msg_data = c.fetch(num, '(RFC822)') # fetches entire message
            typ, msg_data = c.fetch(num, '(FLAGS BODY.PEEK[HEADER])') # just gets header and flags
            if r'\Deleted' in msg_data[0][0]:
                continue        # ignore deleted messages
            msg = email.message_from_string(msg_data[0][1])
            if 'message-id' not in msg:
                continue        # don't delete messages without a message id
            mid = msg['message-id']
            print "\r",num,mid,msg['subject'],"                     ",
            sys.stdout.flush()
            if mid in seen_messageids:
                print "\n","delete ",num,msg['subject']
                t,r = c.store(num, '+FLAGS', r'(\Deleted)')
                total_deleted += 1
            seen_messageids.add(mid)
    except KeyboardInterrupt:
        print "KeyboardInterrupt!"
        os.exit(1)
    typ, response = c.expunge()
    print 'Expunged:', response
    print "Total Deleted:",total_deleted

if __name__=="__main__":
    import slgimap,imaplib
    M = slgimap.connection(imaplib)
    (res,data) = M.list()
    assert res=='OK'
    for line in data:
        print line
        flags, delimiter, mailbox_name = list_response_pattern.match(line).groups()
        if ("Archive" in mailbox_name) or ("All Mail" in mailbox_name):
            print "Removing dups in",mailbox_name
            remove_dups(M,mailbox_name)
        
    M.close()
    M.logout()
            
