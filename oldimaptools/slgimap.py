"""Create a connection to one of Simosn's mail servers
Can be used with multiple imap client implementations
"""


# import imaplib2
# http://www.doughellmann.com/PyMOTW/imaplib/index.html

# to undelete a message:
#c.store(num, "-FLAGS", r'(\Deleted)') # undelete

def connection(lib):
    import sys,os

    if len(sys.argv)<2:
        print "usage: %s [me|nps npspassword]"
        print "me password should be in ~/.me"
        exit(1)

    if sys.argv[1]=='me':
        username = 'simsong'
        password = open( os.getenv("HOME")+"/.me").read().strip()
        server = 'mail.me.com'

    if sys.argv[1]=='nps':
        username = 'slgarfin'
        password = sys.argv[2]
        server = 'smtp.nps.edu'

    if sys.argv[1]=='gmail':
        username = 'simsong'
        password = sys.argv[2]
        server = 'imap.gmail.com'

    if sys.argv[1]=='rackspace':
        server = 'secure.emailsrvr.com'
        username = 'slg@garfinkel.org'
        password = sys.argv[2]

    M = lib.IMAP4_SSL(server)
    M.service = sys.argv[1]
    M.debug=1
    #M = lib.IMAP4(server)
    r, msg = M.login(username,password)
    if r!='OK':
        print "r=",r
        raise ValueError,"Could not log into imap server "+server+" username="+username+" password="+password
    return M


def archive_mbox(M):
    r,boxes = M.list()
    assert r=='OK'
    boxes = filter(lambda s:"Deleted" not in  s, boxes)
    boxes = filter(lambda s:"Archive" in s , boxes)
    boxes = [x.split(" ")[-1] for x in boxes]
    return boxes[0]
