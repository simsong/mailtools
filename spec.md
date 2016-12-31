Initial Goals
=============

Analyze a mailing list archive, reporting:
 * Who joined, and when
 * # of active participants in each month
 * Who introduces new discussions, and who follows
 * Average time between postings and a response, per user
 * Total messages/month / # of active threats.

More questions to answer:
* When did I email this person last?
* When did they last email me?
* Typiucal time between volly?
* Date of first email
* Length of relationship
* new to follow-up ratio.



Database Schema
===============
We will borrow as much as possible from the Apple Mail V4 Schema. 

* It's a well-thought-out database used in production.
* If we mirror it, the analysis code will be able to work on Apple mail stores as-is, without importing.


Apple Schema - What I've learned
  CREATE TABLE messages (ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
                         message_id,
                         document_id BLOB,
                         in_reply_to,
                         remote_id INTEGER,
                         sender INTEGER,
                         subject_prefix,                // combine with subjects.rowid[subject] to get the subject
                         subject INTEGER,
                         date_sent INTEGER,
                         date_received INTEGER,
                         date_created INTEGER,
                         date_last_viewed INTEGER,
                         mailbox INTEGER,
                         remote_mailbox INTEGER,
                         flags INTEGER,
                         read,
                         flagged,
                         size INTEGER,
                         color,
                         type INTEGER,
                         conversation_id INTEGER DEFAULT -1,
                         snippet TEXT DEFAULT NULL,
                         fuzzy_ancestor INTEGER DEFAULT NULL,
                         automated_conversation INTEGER DEFAULT 0,
                         root_status INTEGER DEFAULT -1,
                         conversation_position INTEGER DEFAULT -1,
                         deleted INTEGER DEFAULT 0);


  CREATE TABLE subjects (ROWID INTEGER PRIMARY KEY,                // rowid is messages.subject
                         subject COLLATE RTRIM,
                         normalized_subject COLLATE RTRIM);

  CREATE TABLE addresses (ROWID INTEGER PRIMARY KEY,
                          address COLLATE NOCASE,
                          comment,
                          UNIQUE(address, comment));


  CREATE TABLE "recipients" (ROWID INTEGER PRIMARY KEY,
                          message_id INTEGER NOT NULL REFERENCES messages(ROWID) ON DELETE CASCADE,
                          type INTEGER,                            // what is this?
                          address_id INTEGER NOT NULL REFERENCES addresses(ROWID) ON DELETE CASCADE,
                          position INTEGER);                       // is this to vs. cc? 


Notice unusual sqlite3 commands:
  COLLATE RTRIM
  COLLATE NOCASE
  ON DELETE CASCADE



      When you want a message subject, you need to combine the subject and the 

Apple Schema - triggers are used for much of the database work:

* CREATE TRIGGER before_delete_message BEFORE DELETE ON messages

* CREATE TRIGGER after_delete_message AFTER DELETE ON messages

* CREATE TRIGGER after_insert_message AFTER INSERT ON messages

* CREATE TRIGGER after_insert_message_unread AFTER INSERT ON messages WHEN (NEW.flags&1 = 0 AND NEW.flags&2 = 0)

* CREATE TRIGGER after_update_message AFTER UPDATE OF flags ON messages

* CREATE TRIGGER after_update_message_becoming_read AFTER UPDATE OF flags ON messages WHEN (OLD.flags&1 = 0 AND OLD.flags&2 = 0) AND (NEW.flags&1 != 0 OR NEW.flags&2 != 0)

* CREATE TRIGGER after_update_duplicates_unread_count_becoming_unread AFTER UPDATE OF unread_count ON duplicates_unread_count WHEN OLD.unread_count = 0 AND NEW.unread_count = 1

* CREATE TRIGGER after_update_duplicates_unread_count_becoming_unread AFTER UPDATE OF unread_count ON duplicates_unread_count WHEN OLD.unread_count = 0 AND NEW.unread_count = 1

* CREATE TRIGGER after_update_duplicates_unread_count_becoming_read AFTER UPDATE OF unread_count ON duplicates_unread_count WHEN OLD.unread_count = 1 AND NEW.unread_count = 0

* CREATE TRIGGER after_insert_label AFTER INSERT ON labels

* CREATE TRIGGER after_delete_label AFTER DELETE ON labels



Desired Reports
===============
For MAILING-LIST
- Each month
- Who started being active (first appearance from the email address)
- Who stopped being active
Create a graph:

    <------ Email1 -------->
       <-----------Email2------>
         <-----Email3----->

Can we do the same with topics?

To create this report:

Select (email address, first appearance, last appearance, count)

Each email address may be a collection of numbers, so the easiest way to do this is loop on each.

def get_address_ids(email):
  return set(select rowid from addresses where address=email)

  to_ids = get_address_ids(MAILING-LIS)T
  distinct_emails = select distinct address from addresses
  for email in distinct_emails: 
    ids = get_address_ids(email)
    select min(date_sent),max(date_sent),count(*) from messages where sender in ids and message_id in (select message_id from recepients where address_id in to_ids);

