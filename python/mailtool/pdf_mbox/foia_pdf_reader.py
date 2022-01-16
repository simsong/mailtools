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


def use_pymupdf(fname):
    import fitz
    doc = fitz.open(fname)
    for page in doc:
        count = 0
        if page.number!=871:
            continue

        print("Subject:", get_label_text(page, 'Subject:'))
        print("Date:", get_label_text(page,"Date:"))
        exit(0)

        for lnk in page.get_links():
            print(lnk)
            if is_mailto(lnk):
                label = get_link_label(page, lnk)
                print(page.number, label, lnk['uri'])
                count += 1
        if count>0:
            print('\n')


if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Read a PDF file and digest it.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("pdffile", help="PDF File to analyze")
    args = parser.parse_args()
    use_pymupdf(args.pdffile)
