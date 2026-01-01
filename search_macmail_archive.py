import os
import email
import sys
from email.utils import parseaddr
from email import policy
from collections import OrderedDict
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
import quopri
import re
import pandas as pd
from bs4 import BeautifulSoup


records = []

def html_to_text(html):
    loc = html.find("</html")
    if loc>0:
        html = html[0:loc]
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(separator='\n')

def extract_fields_from_plaintext(text):
    fields = OrderedDict()
    lines = text.strip().splitlines()
    field_keys = {
        'name', 'email', 'institution', 'title',
        'url', 'undergraduates', 'graduates', 'domestic'
    }
    comment_lines = []
    in_comment = False

    for line in lines:
        # Remove soft linebreaks and decode quoted-printable remnants
        line = quopri.decodestring(line.encode('utf-8')).decode('utf-8', errors='replace').strip()

        if in_comment:
            comment_lines.append(line)
        else:
            match = re.search(r'([A-Za-z]+):\s*(.*)$', line)
            if match:
                k, v = match.group(1).lower(), match.group(2).strip()
                if k in field_keys:
                    fields[k] = v
            else:
                if fields:
                    in_comment = True

    comment = '\n'.join(comment_lines).strip()
    if comment.startswith("<html>"):
        comment = html_to_text(comment)
    fields['comment'] = comment
    return fields

def extract_visible_text_from_html(html_bytes):
    # Decode quoted-printable and UTF-8
    html = quopri.decodestring(html_bytes).decode('utf-8', errors='replace')
    return html_to_text(html)

def get_msg_text(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_content()
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                return extract_visible_text_from_html(part.get_payload(decode=True))
        print('ERROR')
        print('ERROR')
        print(msg)
        raise ValueError("No text/plain or text/html found.")
    text = msg.get_content()
    if text.startswith("<html>"):
        text = html_to_text(text)
    return text


def process_msg(msg):
    name, addr = parseaddr(msg['to'])
    if addr!='m57_mail@digitalcorpora.org':
        return
    text = get_msg_text(msg)
    fields = extract_fields_from_plaintext(text)
    try:
        dt = parsedate_to_datetime(msg['date'])
        fields['date'] = dt.isoformat()
        records.append(fields)
    except KeyError as e:
        print("fields=",fields)
        print("text:",text)
        raise

def process_emlx(fname):
    with open(fname,'rb') as f:
        length_line = f.readline()
        try:
            content_length = int(length_line.strip())
        except ValueError:
            print("Invalid .emlx file format: can't read length prefix")
            return
        msg = BytesParser(policy=policy.default).parse(f)
        process_msg(msg)


def iter_mbox_messages(mbox_path):
    mbox = mailbox.mbox(mbox_path, factory=None)  # Don't parse yet
    for message in mbox:
        raw = message.as_bytes()
        yield BytesParser(policy=policy.default).parsebytes(raw)


def iter_maildir_messages(maildir_path):
    maildir = mailbox.Maildir(maildir_path, factory=None)
    for message in maildir:
        raw = message.as_bytes()
        yield BytesParser(policy=policy.default).parsebytes(raw)


def is_mbox_file(path):
    with open(path, 'rb') as f:
        first_line = f.readline()
        return first_line.startswith(b'From ')

def process_path(path):
    if path.endswith('.plist') or path.endswith('.dontIndex'):
        return
    if path.endswith('.emlx'):
        try:
            process_emlx( path )
        except KeyError as e:
            print("Key Error in",path)
        return
    if is_mbox_file( path ):
        for msg in iter_mbox_messages( path ):
            try:
                process_msg(msg)
            except ValueError as e:
                print("ERROR, continuing in",path)
        return
    print("Unknown file type:",path,end='\r')

def process_dir(the_dir):
    for (root,dirs,files) in os.walk(the_dir):
        if '/Attachments/' in root:
            continue
        for fname in files:
            process_path( os.path.join(root,fname) )



# Matches all illegal XML characters (control chars not allowed in Excel)
_illegal_characters_re = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

def clean_illegal_chars(val):
    if isinstance(val, str):
        # Remove illegal control characters
        val = _illegal_characters_re.sub("", val)
        # Try to convert to int or float
        if val.isdigit():
            return int(val)
        try:
            return float(val)
        except ValueError:
            return val

        return _illegal_characters_re.sub("", val)
    return val

def clean_dataframe(df):
    return df.apply(lambda col: col.map(clean_illegal_chars))

if __name__=="__main__":
    import argparse
    parser = argparse.ArgumentParser(description='search a macmail archive',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("path")
    args = parser.parse_args()
    if os.path.isdir(args.path):
        process_dir(args.path)
    else:
        process_path(args.path)
    df = pd.DataFrame(records)
    df = clean_dataframe(df)

    dfa = df[df['email'].str.lower().str.endswith(('.com', '.edu', '.us'), na=False)]
    dfa.to_excel('records-us..xlsx', index=False)

    dfa = df[~df['email'].str.lower().str.endswith(('.com', '.edu', '.us'), na=False)]
    dfa.to_excel('records-notus..xlsx', index=False)
