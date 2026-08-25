# Mail Tools

This is an umbrella and historical repository for programs that process or
analyze email. The actively developed personal preservation application has
moved to the standalone
[`simsong/mail-archiver`](https://github.com/simsong/mail-archiver)
repository, with its own packaging, tests, documentation, and CI.

The remaining programs range from useful specialty tools to research
prototypes and preserved legacy code. Review each tool before connecting it to
a live mailbox.

## Specialty tools

* [`gmail_deduplicate/`](gmail_deduplicate/) removes Gmail messages carrying
  Apple Mail's `X-Apple-Auto-Saved` header. It permanently deletes remote mail,
  has no dry-run mode, and must be treated as a destructive alpha utility.
* [`imap_copy.py`](imap_copy.py) lists or downloads one IMAP mailbox and can
  upload an MBOX to `INBOX`. It does not provide durable UID checkpointing or
  destination verification.
* [`python/mailtool/imaptool.py`](python/mailtool/imaptool.py) lists folders,
  reports status, inspects envelopes, and downloads a folder to MBOX. Its
  client-side cache and incremental synchronization remain incomplete.
* [`autoresponder.py`](autoresponder.py) and
  [`search_macmail_archive.py`](search_macmail_archive.py) implement an older
  mail-driven form workflow. The autoresponder can delete and expunge source
  messages and is not safe for general deployment without additional controls.
* [`python/mailtool/pdf_mbox/`](python/mailtool/pdf_mbox/) is an experimental
  FOIA PDF email-extraction project with legacy dependencies.
* [`macos_addressbook_extract.py`](macos_addressbook_extract.py) extracts data
  from an older macOS Address Book database schema.

## Historical material

The `legacy/`, `python/mailtool/albert/`, `python/timewheels/`, `gui_demo/`,
and `ref/` trees contain older software, teaching and research prototypes, or
third-party reference material. They are retained for history and should not
be mistaken for supported applications.

## Gmail access

Gmail IMAP access normally requires an application-specific password:

1. Request an app password from
   <https://support.google.com/mail/answer/185833>.
2. See Google's IMAP/SMTP documentation at
   <https://developers.google.com/gmail/imap/imap-smtp>.

## See also

* [mail-archiver](https://github.com/simsong/mail-archiver)
* [Email Mining Toolkit](https://github.com/hjast/NLPWorkspace)
* [mail-trends](https://github.com/mihaip/mail-trends)
