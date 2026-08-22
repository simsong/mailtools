# Integrity controls

## Status

This document specifies the durable integrity sidecar format for canonical
MBOX files. The program is under development; only this format is supported.
`requirements.md`, `implementation.md`, the writer, recovery path, standalone
verifier, and substantive tests use this format.

## Goals

Each canonical MBOX needs a self-describing integrity sidecar that can:

* identify the sidecar format before interpreting any digest;
* define each hash standard once at the top of the file;
* give each defined standard a short code such as `h1`;
* tag every stored digest with its defining code;
* carry multiple hash standards and digest algorithms concurrently;
* verify the complete MBOX byte stream and every ordered message;
* retain enough information to recover original RFC 5322 bytes where MBOX
  quoting is ambiguous;
* support streaming generation and verification with the Python standard
  library;
* remain deterministic when regenerated from unchanged canonical inputs; and
* evolve without changing the meaning of an existing digest.

The sidecar detects accidental corruption and inconsistent publication. It is
not an authenticated signature: an attacker able to replace both the MBOX and
the sidecar can manufacture matching digests. Authenticity would require a
separate signature rooted in a key or independently stored digest.

## Terminology

These terms are distinct:

* A **digest algorithm** is a cryptographic primitive such as SHA-256 or
  SHA-512.
* A **hash standard** defines the scope, source-byte recovery, selected
  fields, canonicalization, framing, digest algorithm, and output encoding.
* A **hash-standard version** fixes those rules for the lifetime of the
  standard.
* A **hash code** is a short file-local alias such as `h1` for one complete
  versioned hash-standard declaration.
* A **format version** defines the control records and TSV grammar.
* A **manifest generation** describes one exact byte generation of one MBOX.

SHA-256 itself does not have a mailarchiver version. A complete declaration
combines a versioned input standard with a digest algorithm. For example, one
code can mean semantic standard version 1 with SHA-256, while another means
the same semantic input with SHA-512.

Once declared, the meaning of a hash-standard name and version is immutable.
Any change to recovery, selection, canonicalization, ordering, framing,
algorithm, or encoding requires a different declaration and code.

## Filename

The sidecar filename is:

```text
NAME.mbox.integrity
```

For example:

```text
2024-Archive1.mbox
2024-Archive1.mbox.integrity
```

The file is not named `.jsonl` because only its control section is JSON Lines.
The message section is TSV. The complete MBOX filename remains in the sidecar
name so missing and orphan sidecars can be found without parsing their
contents.

## Hybrid encoding

The sidecar deliberately uses two encodings:

1. JSON Lines at the top for format identification, hash-standard
   declarations, MBOX metadata, and the message-table transition; and
2. TSV for the large, dense, homogeneous list of per-message hashes.

JSON makes the small control section explicit and extensible. TSV avoids
repeating JSON object keys and descriptions for every message. Both sections
are streamable and require only Python's standard library.

Each hash-standard declaration assigns a short code:

```text
h1
h2
h3
```

Every digest outside its declaration is represented as:

```text
CODE:LOWERCASE_HEX_DIGEST
```

For example:

```text
h1:5d41402abc4b...
h2:a91d...
h3:bbc7...
```

The code, not column position or digest length, determines the hash-standard
version, digest algorithm, scope, and canonicalization. Multiple digest types
can therefore occur in one sidecar and on one TSV message line.

## File sequence

The UTF-8 file contains, in order:

1. exactly one `integrity-manifest` JSON record;
2. one `hash-standard` JSON record for each code;
3. exactly one `mbox` JSON record;
4. exactly one `message-table` JSON record;
5. exactly one TSV header line; and
6. one TSV data line for each MBOX message, in MBOX order.

The `message-table` record is the final JSON record and changes the grammar to
TSV. All remaining lines use the declared TSV grammar through end of file.
Version 1 does not permit blank lines, comments, a byte-order mark, or records
after the TSV table.

## Structural example

Actual JSON records occupy one compact physical line each:

```json
{"format_id":"tag:simson.net,2026:mailarchiver/integrity","format_version":1,"manifest_id":"h1:5d41402abc4b...","type":"integrity-manifest"}
{"canonicalization":{"method":"none"},"code":"h1","digest_algorithm":"sha256","hash_standard":"mbox","hash_version":1,"id":"tag:simson.net,2026:mailarchiver/hash/mbox/v1/sha256","input":"complete-mbox-file","scope":"mbox","type":"hash-standard"}
{"canonicalization":{"method":"none"},"code":"h2","digest_algorithm":"sha256","hash_standard":"raw","hash_version":1,"id":"tag:simson.net,2026:mailarchiver/hash/raw/v1/sha256","input":"recovered-rfc5322-message","scope":"message","type":"hash-standard"}
{"canonicalization":{"body":{"length":"entire","method":"dkim-simple"},"domain_separator":"tag:simson.net,2026:mailarchiver/hash/semantic/v1\u0000","headers":{"method":"dkim-relaxed","occurrences":"all","order":["from","sender","reply-to","to","cc","bcc","delivered-to","date","message-id","subject","mime-version","content-type","content-transfer-encoding","content-disposition"],"repeated_field_order":"bottom-to-top"},"line_endings":"crlf-from-crlf-lf-or-cr"},"code":"h3","digest_algorithm":"sha256","hash_standard":"semantic","hash_version":1,"id":"tag:simson.net,2026:mailarchiver/hash/semantic/v1/sha256","input":"recovered-rfc5322-message","scope":"message","type":"hash-standard"}
{"code":"h4","digest_algorithm":"sha512","hash_standard":"semantic","hash_version":1,"id":"tag:simson.net,2026:mailarchiver/hash/semantic/v1/sha512","same_input_as":"h3","scope":"message","type":"hash-standard"}
{"bytes":18293473,"hashes":["h1:5d41402abc4b..."],"messages":2,"name":"2024-Archive1.mbox","type":"mbox"}
{"columns":["ordinal","message-id-json","hashes..."],"encoding":"tsv","type":"message-table"}
```

`h3` contains the complete semantic-input definition. `h4` explicitly reuses
those input bytes with a different digest algorithm.

The next physical line is the literal TSV header, followed by TSV data:

```text
ordinal<TAB>message-id-json<TAB>hashes...
1<TAB>"first@example.net"<TAB>h2:a91d...<TAB>h3:bbc7...<TAB>h4:c482...
2<TAB>"second@example.net"<TAB>h2:e320...<TAB>h3:194c...<TAB>h4:0a52...
```

`<TAB>` represents one ASCII tab byte in this displayed example.

## Manifest record

The first line has these required fields:

* `type` is `integrity-manifest`.
* `format_id` is the permanent global format discriminator.
* `format_version` is the control and table grammar version.
* `manifest_id` identifies the exact MBOX generation.

Version 1 derives `manifest_id` from the first declared MBOX-scope hash:

```text
CODE:LOWERCASE_HEX_DIGEST
```

The required primary MBOX declaration is SHA-256 over the complete MBOX. Its
code is normally `h1`. This identifier is deterministic and recoverable from
the MBOX; a random UUID would not be.

## Hash-standard records

Each declaration has:

* a unique file-local `code` matching `h[1-9][0-9]*`;
* an immutable global `id`;
* a `hash_standard` name;
* an integer `hash_version`;
* a lowercase `digest_algorithm` token;
* a scope of `mbox` or `message`;
* an input definition; and
* complete machine-readable canonicalization rules or `same_input_as`.

Codes must be declared consecutively as `h1`, `h2`, and so on. They are local
aliases, not permanent global identifiers. The global `id` provides permanent
identification when a declaration is copied elsewhere.

Supported version 1 algorithm tokens are the lowercase `hashlib` names
`sha256` and `sha512`. A digest following the code is lowercase hexadecimal of
the exact length required by that declaration.

Two declarations may share the same hash-standard name and version while
using different digest algorithms. The first contains the complete input and
canonicalization definition. A later declaration may use `same_input_as` to
name that earlier code instead of repeating the definition. It must have the
same scope, hash-standard name, and hash version. References must point
backward and may not form chains. A generator should feed the shared bytes to
all requested digest algorithms in one pass.

## MBOX record

The MBOX record binds the sidecar to a filename, byte length, message count,
and every declared MBOX-scope hash:

```json
{"bytes":18293473,"hashes":["h1:5d41402abc4b..."],"messages":2,"name":"2024-Archive1.mbox","type":"mbox"}
```

Every declared MBOX-scope code must occur exactly once in `hashes` in numeric
code order. Message-scope codes must not occur there. Byte length and message
count are integrity assertions, not hints.

## TSV declaration and header

The `message-table` record declares three logical columns:

```json
{"columns":["ordinal","message-id-json","hashes..."],"encoding":"tsv","type":"message-table"}
```

The literal TSV header immediately following it must be exactly:

```text
ordinal<TAB>message-id-json<TAB>hashes...
```

`hashes...` means one TSV field for every declared message-scope hash code.
The declaration and literal header are both required: the JSON record marks
the grammar transition, while the TSV header makes the table independently
intelligible.

## TSV message records

`ordinal` is a one-based decimal integer. It is contiguous and strictly
increasing.

`message-id-json` is the normalized Message-ID encoded as one JSON string
scalar, or the literal JSON token `null` when no Message-ID exists. JSON string
escaping prevents a malformed identifier containing a tab, newline, quote, or
backslash from changing the TSV structure. The field is diagnostic metadata;
the verifier must not use it in place of bytes selected by a hash standard.

Every remaining field is one `CODE:DIGEST` value. Each declared message-scope
code must occur exactly once, in numeric code order. MBOX-scope codes,
undeclared codes, duplicate codes, missing codes, empty fields, extra fields,
uppercase hex, and whitespace around a field are invalid.

The table is dense: every message has every declared message-scope hash.
Adding a hash standard or digest algorithm requires regenerating the sidecar
with its new code populated for every applicable message.

Tagging every digest makes each value self-identifying even if a line is
examined without the TSV header. It also prevents a reader from silently
assigning a valid-looking digest to the wrong standard because columns were
reordered.

## Initial hash standards

### MBOX version 1

The input is every byte of the named MBOX file, including MBOX separators,
quoting, record terminators, and line endings. It is the primary test that the
canonical container has not changed.

The required declaration uses SHA-256 and is normally assigned `h1`. Another
code may define SHA-512 over the identical MBOX byte stream.

### Raw message version 1

The input is the recovered original RFC 5322 message bytes. The MBOX `From `
separator and MBOX storage quoting are not part of the message. No header,
body, line-ending, MIME, whitespace, or character-set canonicalization is
applied.

The exact recovery procedure is part of this standard. Mailarchiver must
consider the bounded interpretations of ambiguous `>From ` lines and select
only a candidate whose declared raw-message digests match. A sidecar generator
must not replace the original digest with a hash of an arbitrary MBOX-reader
interpretation.

Raw-message hashes support byte-preserving retrieval, verification,
publication recovery, and forensic comparison. They are not semantic
deduplication hashes. The required declaration uses SHA-256 and is normally
assigned `h2`.

### Semantic message version 1

Semantic version 1 provides a conservative, delivery-aware identity derived
from DKIM canonicalization rules. Its input is the RFC 5322 candidate selected
by the raw-message hash. References to DKIM mean the canonicalization
algorithms in RFC 6376, not the use or verification of a message's
`DKIM-Signature` field.

The canonical byte stream is:

```text
UTF8("tag:simson.net,2026:mailarchiver/hash/semantic/v1")
NUL
canonical selected header fields
CRLF
DKIM-simple canonical body
```

The domain separator prevents a digest computed for another application or
profile from being mistaken for semantic version 1.

Before header scanning, line endings are converted to DKIM's required CRLF
network-normal representation. A CR followed by LF is one line ending; a bare
CR or bare LF is also one line ending. Every recognized line ending is emitted
as CRLF, and all other octets remain unchanged. This conversion never changes
canonical MBOX bytes or raw-message hashes.

Headers are visited in this fixed order:

```text
From
Sender
Reply-To
To
Cc
Bcc
Delivered-To
Date
Message-ID
Subject
MIME-Version
Content-Type
Content-Transfer-Encoding
Content-Disposition
```

For each name, all occurrences are selected and emitted from the physical
bottom of the header block to the top, matching DKIM repeated-field selection.
Each selected field is canonicalized using DKIM relaxed header
canonicalization:

* lowercase the field name;
* unfold continuation lines;
* reduce each sequence of space or tab to one space;
* remove trailing whitespace from the unfolded value; and
* remove whitespace adjacent to the colon.

Header values are not decoded, address-normalized, MIME-decoded, reordered, or
case-folded. An empty field emits its canonical field name, colon, and CRLF. An
absent field emits no bytes.

After the selected fields, one CRLF separates the header stream from the body.
The complete encoded MIME body, including attachments and nested MIME part
headers, is canonicalized with DKIM simple body canonicalization. It removes
surplus empty lines at the end and ensures one final CRLF but makes no other
body change. DKIM's optional `l=` body-length limit is prohibited.

`Delivered-To` is deliberately delivery-sensitive. A sent copy without it and
a received copy with it remain distinct. Multiple occurrences retain their
delivery sequence. If a source strips `Delivered-To`, deduplication may retain
an additional copy; this safe false negative is preferable to collapsing
deliveries without evidence.

Local state and transport annotations are deliberately excluded, including:

* `Status` and `X-Status`;
* `Received` and `Return-Path`;
* `Authentication-Results` and similar verifier annotations; and
* `DKIM-Signature` and other signatures.

Raw-message hashes remain authoritative for byte integrity because even DKIM
simple body canonicalization treats differing terminal empty lines as
equivalent. SHA-256 and SHA-512 declarations may both cover the identical
semantic version 1 byte stream, using separate codes.

## Malformed input

Integrity generation must not discard a message because selected metadata is
malformed. Every retained message receives every declared message-scope hash.
Semantic version 1 uses a byte-oriented RFC 5322 header scan:

* the first empty line ends the header block;
* a recognizable field begins with a field name and colon;
* a line beginning with space or tab continues the preceding recognizable
  field;
* unrecognized header lines are omitted from the selected-header stream but
  remain protected by raw-message hashes; and
* if no header/body separator exists, the complete input is the header block
  and the body is empty.

These rules keep semantic hashing independent of Unicode decoding and display
parsing.

## Deterministic serialization

Version 1 requires:

* UTF-8 without a byte-order mark;
* compact JSON control records terminated by LF;
* lexicographically sorted JSON object keys at every nesting level;
* JSON separators `,` and `:` without optional surrounding whitespace;
* hash codes declared consecutively in numeric order;
* one literal ASCII tab between TSV fields and LF after every TSV line;
* lowercase hexadecimal digest values;
* messages in canonical MBOX order; and
* no creation time, generator version, host path, or other volatile value.

Regenerating the sidecar from unchanged canonical inputs and declarations must
reproduce identical bytes.

## Validation behavior

A verifier reports separate results for:

1. control structure and deterministic encoding;
2. supported, complete, and internally consistent hash-standard declarations;
3. MBOX filename, byte length, count, and every MBOX-scope hash;
4. the message-table declaration and literal TSV header;
5. ordered raw-message recovery and every declared raw digest; and
6. every declared semantic digest.

An unknown format version cannot be verified. A known format containing an
unknown required hash standard may be checked only partially; the verifier
must report partial verification and return nonzero. It must never print an
unqualified success while any declared digest remains unchecked.

Malformed JSON, duplicate JSON keys, nonconsecutive codes, inconsistent
standard declarations, missing or duplicate TSV codes, noncontiguous
ordinals, wrong digest lengths, count mismatches, unsupported algorithms, and
orphan sidecars are errors.

## Evolution

Evolution follows these rules:

* Never modify the meaning of an existing format ID and version.
* Never modify the meaning of an existing hash-standard name and version.
* A canonicalization change creates a new standard version.
* A digest-algorithm change creates another declaration and code over the
  same standard version.
* Retain existing declarations and digests when adding new ones so results
  can be compared directly.
* Do not reuse a global hash-standard ID for different rules.
* Keep raw byte-integrity hashes when semantic standards are added.

One sidecar can therefore declare codes for all of these concurrently:

```text
MBOX version 1 with SHA-256
raw message version 1 with SHA-256
raw message version 1 with SHA-512
semantic message version 1 with SHA-256
semantic message version 1 with SHA-512
semantic message version 2 with SHA-256
```

Every TSV value remains compact and self-identifying as `hN:digest`.

## Publication and recovery

The sidecar is durable archive content adjacent to its MBOX. It must be
written to a temporary sibling, flushed, and atomically replaced only after
the complete MBOX and every message have been read successfully. Publication
must not expose a sidecar that claims a partially scanned generation.

The content-derived manifest ID, complete-file hashes, byte length, and
message count bind the sidecar to one MBOX generation. If a process stops
between MBOX and sidecar publication, the existing sidecar fails against the
new MBOX rather than silently validating it. Publication recovery must refresh
the sidecar after resolving any pending append.

The installed verifier remains dependency-free. JSON control records, TSV,
SHA-256, SHA-512, RFC 5322 header scanning, DKIM canonicalization, and MBOX
streaming can all be implemented with the Python standard library and compact
local code.

## Required implementation validation

Implementation is incomplete until substantive tests demonstrate:

* deterministic regeneration;
* whole-MBOX corruption detection;
* per-message body, stable-header, and attachment corruption detection;
* equivalence under permitted DKIM header refolding and terminal-body-line
  changes;
* inequality when `Delivered-To`, another selected header, or body content
  changes;
* equivalence when only `Status`, `X-Status`, or excluded trace headers change;
* multiple and missing selected headers, including ordered `Delivered-To`;
* malformed headers, invalid encodings, missing header/body separators, and
  mixed line endings;
* MBOX `From ` quoting recovery using raw-message hashes;
* multiple digest algorithms for one hash-standard version;
* simultaneous verification of multiple hash-standard versions;
* rejection of unknown, missing, duplicate, or out-of-order hash codes;
* interrupted atomic publication and recovery; and
* exclusive use of the required `.mbox.integrity` filename.

The tests must verify the stated byte and semantic behavior, not merely that a
sidecar is emitted or parsed.
