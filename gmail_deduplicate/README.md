# gmail_deduplicate

Apple's Mail.app stores autosave messages in the Gmail archive that can become a huge annoyance.

Fortunately, all of these mail messages are identified with the `X-Apple-Auto-Saved` header.

This vendored tool authenticates to Gmail using OAuth2 and then deletes those
autosave messages.  It is separate from `archiver`, which never changes a
source mailbox.

The program uses Gmail's API with batching. However, because of the
interaction between Mail.app's frequent saves and Gmail rate limits,
the cleanup can take a long time.

## Installation

Install `uv`, create a Google OAuth desktop-client credential, and save it as
`client_secrets.json` in this directory.  The first run opens the OAuth
browser flow and writes `token_gmail.json` locally.

```console
cd gmail_deduplicate
make run
```

## Safety

`make run` issues Gmail `batchDelete` requests for messages carrying the
`X-Apple-Auto-Saved` header.  Gmail deletion is a remote mutation and this
tool currently has no dry-run mode.  Review the code and OAuth account before
running it; never add `client_secrets.json` or `token_gmail.json` to Git.

# Background URLs:
https://developers.google.com/gmail/api/guides/batch
