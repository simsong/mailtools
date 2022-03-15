import os
import os.path
import re

from os.path import dirname,basename,abspath
import fitz

import foia_pdf_reader

PAGE_1142 = os.path.join(dirname( abspath( __file__ )), "1142.pdf")
PAGE_1142_NOUNS = ['CENSUS/ADRM FED',
                   'Catherine Fitch',
                   'Cathy Fitch',
                   'Census',
                   'Co-Director',
                   'Federal Registrar Notice USBC-2018-0009',
                   'John Maron Abowd',
                   'Minnesota Research Data Center' ]

assert os.path.exists(PAGE_1142)

VALID_RE = re.compile(r"([-a-zA-Z0-9/ _.]+)")

def test_foia_pdf_reader():
    doc = fitz.open( PAGE_1142 )
    page = doc[0]
    assert( foia_pdf_reader.is_first_page(page)) == True


    pa = foia_pdf_reader.PageAnalyzer(page)

    links = page.get_links()
    assert( len(links) == 7)

    text = page.get_text( 'text' )

    nouns = foia_pdf_reader.extract.v2( text )
    for noun in nouns:
        m = VALID_RE.search(noun)
        assert m is not None
        assert m.group(1) == noun

    for noun in PAGE_1142_NOUNS:
        assert noun in nouns
