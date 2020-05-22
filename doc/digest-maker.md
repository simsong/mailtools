Requirements for a python program that assists in mail processing.

* Behavior determined by a config file that is not part of the repo.  See below for the list of configuration options.


* Maintain a volume number and issue number for the next digest
* Identify mail messages in inbox that contain KEYWORD on the Subject line.
* Download all messages using IMAP.
* Create a table-of-contents with the subject lines for each message.
* Have each of the message following, each numbered. Only keep:
  * Date, From: and Subject: headers
  * Message content. Take the TEXT content if present, otherwise take the HTML content and render as TEXT.
  * Be sure to remove Quote Printable!
* Output processing:
  * Option 1: Save in a file
  * Option 2: Display in a web browser, allowing copy-and-paste into an email system.
  * Option 3: Send to an SMTP server.
  * Option 4:
    * Create digest in Drafts folder so that the user can just review and then click "SEND" with their ordinary mail client.
    * Move articles used in the digest to the Archived box.
    * Move the trash articles (those without the keyword) to the Trash
    * If there are too many articles, save the rest for next time (future option)


## configuration options
This is a sample config file. We'll use traditional Microsoft-style CONFIG.INI files:

```
[imap]
; imap configuration. Program prompts for what's not here:
server: imap.company.com
username: username@company.com
password: MyPassword!

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
