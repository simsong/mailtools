#!/usr/bin/env python3

import sys
import os.path

import nltk
from nltk.tag import pos_tag
from nltk.tokenize import word_tokenize
from nltk.tokenize.treebank import TreebankWordTokenizer

#
# Extract proper nouns
#

def get_nnp_runs(text):

    # First, the punkt tokenizer divides our text in sentences.
    # Each sentence is then tokenized and POS tagged.
    #
    # Proper nouns receive the tags 'NPP', we discard first words of sentence to
    # reduce the false positive rate. For example, in the following sentence,
    # onomatopoeias are tagged as NPP: "Bang! Ssssssss! It exploded.".

    seen = set()

    sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')
    for sentence in sent_detector.tokenize(text):
        tokenizedSentence = word_tokenize(sentence)
        taggedSentence   = pos_tag(tokenizedSentence)
        currentCandidate = []

        # Find the NNP runs
        for (ct, (word, pos)) in enumerate(taggedSentence):
            if ct==0:           # ignore the first
                continue

            if pos == 'NNP':
                currentCandidate.append(word)
                continue

            if len(currentCandidate) > 0:
                nnp_run = ' '.join(currentCandidate)
                if nnp_run not in seen:
                    yield(nnp_run)
                currentCandidate = []

        if len(currentCandidate) > 0:
            nnp_run = ' '.join(currentCandidate)
            yield(nnp_run)

def clean(text):
    text = text.replace("|","")
    text = text.replace("‘","")
    text = text.replace("’","")
    text = text.replace("“","")
    text = text.replace("”","")
    return text.strip()

def v2(text):
    return sorted( set( [t for t in [clean(t) for t in get_nnp_runs(text)] if len(t)>0 ] ) )


if __name__=="__main__":
    import argparse, resource
    parser = argparse.ArgumentParser(description='Extract proper nouns',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("path", help="Files or Directories to scan")
    args = parser.parse_args()
    text = open(args.path).read()
    print("\n".join(v2( text )))
