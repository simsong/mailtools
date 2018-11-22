from macos_addressbook_extract import *

def test_best_email():
    assert 'junk@gmail.com' == best_email(['junk@cse.psu.edu', 'junk@gmail.com'])


