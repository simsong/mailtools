#!/usr/bin/env python3
"""
foia_pdf_reader.py:

Read mail messages from a PDF file resulting from a FOIA request and produce:
1. A mailfile that can be processed with conventional mail processing tools.
2. An index of all the PDF files
3. A database.

"""

DB_SCHEMA="""CREATE TABLE MESSAGES(message_date VARCHAR(20),
                                   sender_email VARCHAR(255),
                                   rcpt_email VARCHAR(255),
                                   subject VARCHAR(255));"""

DB_FILE = 'database.db'         # make changable

import sys
import os
import datetime
import collections
from os.path import abspath,dirname,basename

import ctools.dbfile as dbfile

import nltk_extract as extract
#import rosette_extract as extract

try:
    import fitz
except ImportError as e:
    print("cannot import fitz. please try `python -m pip install --upgrade pip; python -m pip install --upgrade pymupdf`",file=sys.stderr)
    raise e

# https://pdfreader.readthedocs.io/en/latest/index.html
def is_mailto(lnk):
    try:
        return lnk['kind']==2 and lnk['uri'].startswith('mailto:')
    except KeyError:
        return False

def parse_date(datestr):
    if datestr is None:
        return None
    datestr = datestr.strip()
    try:
        return datetime.datetime.strptime(datestr, "%A, %B %d, %Y %I:%M:%S %p")
    except ValueError:
        return datetime.datetime.strptime(datestr, "%B %d, %Y %I:%M:%S %p")

class PageAnalyzer:
    def __init__(self, page):
        self.page = page

    def get_link_label(self, lnk):
        y0 = lnk['from'].y0
        y1 = lnk['from'].y1
        ymid = (y0+y1)/2
        for block in self.page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    bbox = span['bbox']
                    ymin = bbox[1]
                    ymax = bbox[3]
                    if(ymin <= ymid <= ymax):
                        return span['text'].lower().replace(':','')
        return None                 # could not determine

    def get_span(self, text):
        for block in self.page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    if span['text']==text:
                        return span
        return None

    def get_text_following_span(self, span):
        if span is None:
            return None
        ret = []
        for block in self.page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for sp in line['spans']:
                    if span==sp:
                        continue
                    if span['bbox'][1] == sp['bbox'][1] and span['bbox'][3] == sp['bbox'][3]:
                        ret.append(sp['text'])
        return ' '.join(ret)

    def get_label_text(self, text):
        return self.get_text_following_span(self.get_span( text ))

def process_first_page(page):
    pa     = PageAnalyzer(page)
    fields = {}

    for lnk in page.get_links():
        if is_mailto(lnk):
            label = pa.get_link_label( lnk )
            if label:
                val = lnk['uri'].replace('mailto:','')
                if label in fields:
                    fields[label] += ' ' + val
                else:
                    fields[label] = val
    if fields:
        fields['page']    = page.number
        fields['subject'] = pa.get_label_text('Subject:')
        fields['date']    = parse_date(pa.get_label_text("Date:"))
        for f in ['to','from','subject']:
            if f not in fields or fields[f] is None:
                fields[f] = ''
    return fields

def process_page_text(page):
    text = page.get_text('text')
    proper_nouns = extract.v2(text)
    for(ct,line) in enumerate(proper_nouns,1):
        print(ct,line)
    print()

def is_first_page(page=None, blocks=None):
    """Return if the page is a first page (with email message metadata)"""
    if not blocks:
        blocks = page.get_text('blocks')
    return blocks and blocks[0][4].startswith('From:\n')

def page_url(pn):
    return f"<a href='https://cen-2020-001984.dxm-software.com/page/{pn}?format=pdf'>[page {pn}]</a>"

def make_terms_index(fname, index_fname):
    print("<html><body>")
    doc = fitz.open(fname)
    first_page_number = None
    titles = dict()
    pages  = collections.defaultdict(set)
    froms  = dict()
    fields = dict()
    first_page_numbers = dict()
    for page in doc:
        if is_first_page(page = page):
            first_page_number = page.number
            fields            = process_first_page(page)
        if not first_page_number:
            continue
        for noun_phrase in extract.v2( page.get_text( 'text' ) ):
            noun_phrase_lc = noun_phrase.lower()
            titles[ noun_phrase_lc] = noun_phrase
            pages[ noun_phrase_lc ].add( page.number )
            if page.number not in first_page_numbers:
                first_page_numbers[ page.number ] = first_page_number
            if first_page_number not in froms:
                froms[ first_page_number ] = str(fields.get('from','?'))
    for noun_phrase in sorted(titles.keys()):
        if len(pages[noun_phrase]) < 50:
            print(f"<h3>{titles[noun_phrase]}</h3>")
            for page in pages[noun_phrase]:
                print(f"&nbsp;&nbsp;&nbsp;{page_url(page)} {froms.get( first_page_numbers[page] , '?')}<br>")
    print("</body></html>")


def dbload(fname):
    """Load all of the metadata for a page into the database"""
    print("page,date,to,from,subject".replace(",","\t"))
    doc = fitz.open(fname)
    for page in doc:
        if is_first_page(page=page):
            fields = process_first_page(page)
            if False:
                print("\t".join([str(fields['page']),
                                 fields['date'].isoformat(),
                                 fields['to'],
                                 fields['from'],
                                 fields['subject']]))
            else:
                print("Page: ",fields['page'])
                print("From: ",fields['from'])
                print("Subject: ",fields['subject'])
                print("to: ",fields['to'])
                print()

        blocks = page.get_text('blocks')
        if not blocks:
            continue
        if blocks[0][4].startswith('From:\n'):
            process_first_page(page)
        else:
            print("page:",page.number)
        process_page_text(page)

def show_page(fname, page_number):
    """output the HTML for a given page number"""
    doc = fitz.open(fname)
    page = doc.load_page(page_number)
    page.clean_contents()
    print(page.get_text('html'))

if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Read a PDF file and digest it.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("pdffile", help="PDF File to analyze")
    parser.add_argument("--htmlpage", type=int, help="Write HTML for a PDF page (largely for testing)")
    parser.add_argument("--dbload", action='store_true', help='Load a MySQL database')
    parser.add_argument("--terms_index", help='Make an index of the terms')
    args = parser.parse_args()
    if args.htmlpage:
        show_page(args.pdffile, args.htmlpage)
        exit(0)

    if args.dbload:
        dbload(args.pdffile)

    if args.terms_index:
        make_terms_index(args.pdffile, args.terms_index)
