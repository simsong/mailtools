Requirements for a python program that assists in mail processing.

# Design

* Run from the command line on a Macintosh or Linux system.
* Run from a `git clone` of this repo.
* Behavior determined by a config file that is not part of the repo.  See below for the list of configuration options.
* Config file contains and can be  _updated_ on each run with:
  * Volume number and issue number for the next digest
  * Prefix KEYWORD on the Subject line of messages to be considered for inclusion in digest.
* Allow operator to rapidly review messages that ready to be included in next digest
  * Decide which get included and which get thrown out.
  * Decide upon order

## Flow
* Submissions are sent to an email address with a KEYWORD in the subject line.
* Moderator runs a sequence of commands on their Macintosh:
  1. `python digest-maker.py --sync`
  2. emacs table-of-contents.txt
  3. `python digest-maker.py --send`


# Operation


## Sync and Review 
On Startup with `--sync` option
1. read the current digest.txt file, and note the order (if it exists)
2. If the order of the email messages in digest.txt doesn't match the table of contents (TOC) at the top, re-order the messages
3. Review messages in IMAP INBOX, and download messages that aren't in digest.txt
4. save digest.txt

Notes on digest-making:
* For each new message, add its Subject: line to the stop of digest.txt, and add body afterwards
* If (Source) not in subject, scan the body of the message to see if the source can be inferred. (From a URL or keyword of publications.)
* When messages are added, fix any ISO 8501/Unicode issues according to `charset` settting in config file.

Configuration information required:
```
[imap]
server:
username:
password:

[digest]
; keyword specifies mailmessages to consider in the Inbox
keyword: KEYWORD
; which character set to use for outgoing mail: should be ASCII or UTF-8. Case insensitive. 
charset: utf-8
; current volume:
volume: 31
; current issue:
issue: 10
```

## Edit-Digest
1. Initially this will be done with EMACS, but it could become a
   HTML-based application.


## Make-Digest
On Startup:
1. Download all messages using IMAP.
2. Read the table-of-contents
3. Prepare:
   * Digest email (ready to send)
   * Digest JSON (a single document containing data and metadata for message)

Notes on the digest:
* Have each of the message following, each numbered. Only keep:
  * Date, From: and Subject: headers
  * Subject is parsed for (Source) at end in parenthesis
  * Message content. Take the TEXT content if present, otherwise take the HTML content and render as TEXT.
  * Be sure to remove Quote Printable!

## Send-Digest
On Startup:
1. Send email to mailing list
2. POST JSON to web service and/or send it as an attachment to drop box.
3. Create an Archive mailbox for the Volume if it doesn't exist
3. Move messages that were sent from INBOX to Archive mailbox. 

Configuration information required:
```
[smtp]
server:
username:
password:
```

