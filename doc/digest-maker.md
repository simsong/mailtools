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
  2. emacs digest.txt
  3. `python digest-maker.py --send`

* Moderator has two ways to delete messages:
  1. Open up the inbox in IMAP and just delete them.
  2. Put the a deleted keyword in the TOC and re-run `--sync`

# Operation


## Sync and Review 
On Startup with `--sync` option
1. read the current digest.txt file, and note the order (if it exists)
2. If the order of the email messages in digest.txt doesn't match the table of contents (TOC) at the top, re-order the messages
3. Review messages in IMAP INBOX:
  3a. If any have a delete keyword, move them to the trash mailbox.
  3b. If any are referenced in the TOC and now have a delete keyword, move them do the trash mailbox.
  3c. Download messages that aren't in digest.txt and add them to digest.txt (both the TOC and the body)
4. save digest.txt and digest.json
   * digest.txt is a file that is ready to be send to the email server (ready to send)
   * digest.json is a (a single document containing data and metadata for each message)

Notes on digest-making:
* For each new message, add its Subject: line to the stop of digest.txt, and add body afterwards
* If (Source) not in subject, scan the body of the message to see if the source can be inferred. (From a URL or keyword of publications.)
* When messages are added, fix any ISO 8501/Unicode issues according to `charset` settting in config file.
* Keep headers specified by `headers`: typically Date, From, Subject:
* Message content: Take the TEXT content if present, otherwise take the HTML content and render as TEXT.

Configuration information required:
```
[imap]
server:
username:
password:

[digest]
; keyword specifies Subject keyword for messages to include
include: KEYWORD

; messages to automatically delete (e.g. from proofpoint)
delete: KEYWORD1,KEYWORD2,KEYWORD3

; specify headers to keep:
headers: date,from,subject

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


## Send-Digest
You can manually send the digest, or you can send it automatically with the `--send` option.

On Startup with `--send`, runs all of the send actions in the config files. Options include:
1. Send email to mailing list
2. POST JSON to web service and/or send it as an attachment to drop box.
3. Send to an FTP server.
4. Log into a remote Unix system and post to Usenet.
5. Increment the issue number.

Configuration information required:
```
[smtp1]
server:
username:
password:
destination:

[ftp1]
server:
username:
password:
destination: dir/to/destination/NAME.{volume}.{issue}

[https1]
url: https://host/location
method: post


[send-actions]
action1: email smtp1
action2: post https1
action3: ftp ftp1

```

