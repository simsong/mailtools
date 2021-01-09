from bulkmail import *

TEST="""to: %to%
from: %from%
subjec: a test message

Hello %firstname%!

This is a test message
"""


def test_find_fields():
    assert set(["to","from", "firstname"]) == find_fields(TEST)
