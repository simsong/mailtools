# mailstats
Mail Statistics

# Functionality we want
* Basic retrieval tools:
  - List email addresses
  - Dates for sender
  - Dates for sender, and # of emails sent/received per day

* parse all iCal entries in mail
* LDA on email? 
* Top emails every week.


* Report breaks in mail file. (Days on which mail was not received)
* Heatmap of when mail is sent
  - weekday / weekend
  - day of week

* Topic modeling of received messages
  - how many topics?
  - mapping of users to specific topics
  - identify users who email on same topics but do not email each other...?

* Plug-in to Autopsey

# Implementation notes

* Metadata is stored in an sqlite3 databsae.
* The schema we use is the same as used by Apple mail client
  - Makes mail tool  work with Apple Mail out of the box.
  - Schema is well developed, stored in [schema.sql](schema.sql)
* Apple AddressBook groups senders together
  - On non-apple systems, need a tool to do this.



# See Also
* Email Maining Toolkit, Java: https://github.com/hjast/NLPWorkspace
* See also https://github.com/mihaip/mail-trends.git

* Identify people who always CC you a dn askt them to stop.
* Identify email sending times. He map through the day, week.
* tool for assigning a title to a topic model?
