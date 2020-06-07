# Master requirements list

## Features that go into the message extraction and ingest layer
Mail message ingest:
* Support for many mailbox formats including mbox, maildir
* Support for ingesting from an IMAP server. (Question: can you give Autopsey a username & password & server and have it download all the mail?)
* Separately process each email attachment
* Preview attachments.
* Recover deleted Email.
* Support server-ingest for multiple mail servers. (e.g. a MS Exchange Server, hMail Server, Communigate Server etc)

Mail message search:
* Full text index (Autopsey does this with Lucene)
* Hash attachement and compute similarity metrics 

Mail header processing:
* Parse Received-By headers into mail routing table.
* Identify the time zone and convert it to UTC when needed
* Check attachments against hashsets: [click here](https://www.sleuthkit.org/autopsy/help/hash_db.html)

## Features that go into the analysis layer 

### Metadata Analysis (e.g. mail headers)
* List emails without SPF for further analysis
* Extract and understand mail headers created by different mail servers.
  * Plug-in architecture for MS Exchange Server, hMail Server, Communigate Server etc.,
* Check for Spam header lines
* Determining sender’s geographic location
* Identify any abnormility related to the time of the email

### Content Analysis
* Identify Threats: [Threats in Email Communication]https://www.researchgate.net/profile/Gurpal_Chhabra/publication/286053691_Review_of_E-mail_System_Security_Protocols_and_Email_Forensics/links/5665afcd08ae418a786f1f7d/Review-of-E-mail-System-Security-Protocols-and-Email-Forensics.pdf)
* Check email body for suspicuose URL/keywords

### Correlation
* Correlate mail messages with same or similar attachments.
* Integrate the tool with ATT&CK framework to detect suspicious behaviour related to email

## User Interface

## Autopsey Integration

Let's pull out the key features that we will want to implement based on the above list (feel free to edit):


