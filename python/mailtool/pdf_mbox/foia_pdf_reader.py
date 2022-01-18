#!/usr/bin/env python3
"""
foia_pdf_reader.py:

Read mail messages from a PDF file resulting from a FOIA request and produce:
1. A mailfile that can be processed with conventional mail processing tools.
2. An index of all the PDF files
3. A database.

c.f.

Using pymupdf
https://pymupdf.readthedocs.io/en/latest/installation.html
https://www.tutorialexample.com/python-split-and-merge-pdf-with-pymupdf-a-completed-guide/

https://pymupdf.readthedocs.io/en/latest/faq.html#how-to-make-images-from-document-pages

https://www.kirkusreviews.com/book-reviews/len-vlahos/hard-wired/
http://ro.ecu.edu.au/cgi/viewcontent.cgi?article=1721&context=theses

https://stackoverflow.com/questions/27744210/extract-hyperlinks-from-pdf-in-python
https://www.tutorialspoint.com/extract-hyperlinks-from-pdf-in-python
https://www.thepythoncode.com/article/extract-pdf-links-with-python


https://towardsdatascience.com/how-to-extract-the-text-from-pdfs-using-python-and-the-google-cloud-vision-api-7a0a798adc13
https://cloud.google.com/document-ai/docs/process-tables
https://cloud.google.com/vision/docs/pdf
https://aws.amazon.com/blogs/machine-learning/process-text-and-images-in-pdf-documents-with-amazon-textract/
https://aws.amazon.com/blogs/machine-learning/translating-scanned-pdf-documents-using-amazon-translate-and-amazon-textract/
https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/automatically-extract-content-from-pdf-files-using-amazon-textract.html


"""

DB_SCHEMA="""CREATE TABLE MESSAGES(message_date VARCHAR(20),
                                   sender_email VARCHAR(255),
                                   rcpt_email VARCHAR(255),
                                   subject VARCHAR(255));"""

DB_FILE = 'database.db'         # make changable

import sys
import os
import datetime
from os.path import abspath,dirname,basename

import ctools.dbfile as dbfile


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

def get_link_label(page, lnk):
    y0 = lnk['from'].y0
    y1 = lnk['from'].y1
    ymid = (y0+y1)/2
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line['spans']:
                bbox = span['bbox']
                ymin = bbox[1]
                ymax = bbox[3]
                if(ymin <= ymid <= ymax):
                    return span['text']
    return None                 # could not determine

def get_span(page, text):
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line['spans']:
                if span['text']==text:
                    return span
    return None

def get_text_following_span(page, span):
    if span is None:
        return None
    ret = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for sp in line['spans']:
                if span==sp:
                    continue
                if span['bbox'][1] == sp['bbox'][1] and span['bbox'][3] == sp['bbox'][3]:
                    ret.append(sp['text'])
    return ' '.join(ret)

def get_label_text(page, text):
    return get_text_following_span(page, get_span(page, text))


def parse_date(datestr):
    if datestr is None:
        return None
    datestr = datestr.strip()
    try:
        return datetime.datetime.strptime(datestr, "%A, %B %d, %Y %I:%M:%S %p")
    except ValueError:
        return datetime.datetime.strptime(datestr, "%B %d, %Y %I:%M:%S %p")

def dbload(fname):
    print("page,date,to,from,subject".replace(",","\t"))
    doc = fitz.open(fname)
    for page in doc:
        blocks = page.get_text('blocks')
        if not blocks:
            continue
        if not blocks[0][4].startswith('From:\n'):
            continue
        fields = {}

        for lnk in page.get_links():
            if is_mailto(lnk):
                label = get_link_label(page, lnk)
                if label:
                    label =label.lower().replace(':','')
                    val = lnk['uri'].replace('mailto:','')
                    if label in fields:
                        fields[label] += ' ' + val
                    else:
                        fields[label] = val
        if fields:
            fields['page']    = page.number
            fields['subject'] = get_label_text(page, 'Subject:')
            fields['date']    = parse_date(get_label_text(page,"Date:"))
            for f in ['to','from','subject']:
                if f not in fields or fields[f] is None:
                    fields[f] = ''
            print("\t".join([str(fields['page']),fields['date'].isoformat(),fields['to'],fields['from'],fields['subject']]))


def show_page(fname, page_number):
    doc = fitz.open(fname)
    page = doc.load_page(page_number)
    page.clean_contents()
    print(page.get_text('html'))

if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Read a PDF file and digest it.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("pdffile", help="PDF File to analyze")
    parser.add_argument("--htmlpage", type=int, help="Write HTML for page")
    parser.add_argument("--dbload", action='store_true', help='Load a MySQL database')
    args = parser.parse_args()
    if args.htmlpage:
        show_page(args.pdffile, args.htmlpage)
        exit(0)

    dbload(args.pdffile)
