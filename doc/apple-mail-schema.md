# Apple's Mail SQLite3 Schema

Here is Apple's mail schema.

```
(base) simsong@nimi mydata % sqlite3 envelope.sqlite3
-- Loading resources from /Users/simsong/.sqliterc
Run Time: real 0.003 user 0.001229 sys 0.000634
SQLite version 3.31.1 2020-01-27 19:55:54
Enter ".help" for usage hints.
sqlite> .schema
CREATE TABLE messages (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, message_id, document_id BLOB, in_reply_to, remote_id INTEGER, sender INTEGER, subject_prefix, subject INTEGER, date_sent INTEGER, date_received INTEGER, date_created INTEGER, date_last_viewed INTEGER, mailbox INTEGER, remote_mailbox INTEGER, flags INTEGER, read, flagged, size INTEGER, color, type INTEGER, conversation_id INTEGER DEFAULT -1, snippet TEXT DEFAULT NULL, fuzzy_ancestor INTEGER DEFAULT NULL, automated_conversation INTEGER DEFAULT 0, root_status INTEGER DEFAULT -1, conversation_position INTEGER DEFAULT -1, deleted INTEGER DEFAULT 0);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE subjects (ROWID INTEGER PRIMARY KEY, subject COLLATE RTRIM, normalized_subject COLLATE RTRIM);
CREATE TABLE addresses (ROWID INTEGER PRIMARY KEY, address COLLATE NOCASE, comment, UNIQUE(address, comment));
CREATE TABLE recipients (ROWID INTEGER PRIMARY KEY, message_id INTEGER NOT NULL REFERENCES messages(ROWID) ON DELETE CASCADE, type INTEGER, address_id INTEGER NOT NULL REFERENCES addresses(ROWID) ON DELETE CASCADE, position INTEGER);
CREATE TABLE threads (ROWID INTEGER PRIMARY KEY, message_id INTEGER NOT NULL REFERENCES messages(ROWID) ON DELETE CASCADE, reference TEXT, is_originator DEFAULT 0);
CREATE TABLE mailboxes (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, url UNIQUE, total_count INTEGER DEFAULT 0, unread_count INTEGER DEFAULT 0, unseen_count INTEGER DEFAULT 0, deleted_count INTEGER DEFAULT 0, unread_count_adjusted_for_duplicates INTEGER DEFAULT 0, change_identifier, source INTEGER, alleged_change_identifier);
CREATE TABLE ews_folders (ROWID INTEGER PRIMARY KEY, folder_id TEXT UNIQUE ON CONFLICT REPLACE, mailbox_id INTEGER NOT NULL UNIQUE ON CONFLICT REPLACE REFERENCES mailboxes(ROWID) ON DELETE CASCADE, sync_state TEXT);
CREATE TABLE duplicates_unread_count (ROWID INTEGER PRIMARY KEY, message_id TEXT NOT NULL ON CONFLICT IGNORE, mailbox_id INTEGER NOT NULL REFERENCES mailboxes(ROWID) ON DELETE CASCADE, unread_count INTEGER DEFAULT 0, UNIQUE(message_id, mailbox_id));
CREATE TABLE attachments (ROWID INTEGER PRIMARY KEY, message_id INTEGER NOT NULL REFERENCES messages(ROWID) ON DELETE CASCADE, name TEXT, UNIQUE(message_id, name));
CREATE TABLE events (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER NOT NULL REFERENCES messages(ROWID) ON DELETE CASCADE, start_date INTEGER, end_date INTEGER, location TEXT, out_of_date INTEGER DEFAULT 0, processed INTEGER DEFAULT 0, is_all_day INTEGER DEFAULT 0, associated_id_string TEXT, original_receiving_account TEXT, ical_uid TEXT, is_response_requested INTEGER DEFAULT 0);
CREATE TABLE labels (message_id INTEGER REFERENCES messages(ROWID) ON DELETE CASCADE, mailbox_id INTEGER REFERENCES mailboxes(ROWID) ON DELETE CASCADE, PRIMARY KEY(message_id, mailbox_id)) WITHOUT ROWID;
CREATE TABLE imap_messages (
ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
message INTEGER REFERENCES messages(ROWID) ON DELETE SET NULL,
mailbox INTEGER REFERENCES mailboxes(ROWID) ON DELETE CASCADE,
flags INTEGER,
uid INTEGER);
CREATE TABLE local_message_actions (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, mailbox INTEGER REFERENCES mailboxes(ROWID) ON DELETE CASCADE, action_type INTEGER, activity_type INTEGER, user_initiated BOOL, flags INTEGER, mask INTEGER);
CREATE TABLE action_imap_messages (ROWID INTEGER PRIMARY KEY, action INTEGER REFERENCES local_message_actions(ROWID) ON DELETE CASCADE, imap_uid INTEGER, date_seen REAL);
CREATE TABLE action_ews_messages (ROWID INTEGER PRIMARY KEY, action INTEGER REFERENCES local_message_actions(ROWID) ON DELETE CASCADE, ews_item_id TEXT);
CREATE TABLE action_messages (ROWID INTEGER PRIMARY KEY, action INTEGER REFERENCES local_message_actions(ROWID) ON DELETE CASCADE, message INTEGER REFERENCES messages(ROWID) ON DELETE SET NULL);
CREATE TABLE action_labels (ROWID INTEGER PRIMARY KEY, action INTEGER REFERENCES local_message_actions(ROWID) ON DELETE CASCADE, do_add INTEGER, label INTEGER REFERENCES mailboxes(ROWID) ON DELETE CASCADE);
CREATE TABLE imap_copy_action_messages (ROWID INTEGER PRIMARY KEY, action INTEGER REFERENCES local_message_actions(ROWID) ON DELETE CASCADE, source_message_uid INTEGER, source_message INTEGER REFERENCES messages(ROWID) ON DELETE SET NULL, destination_message INTEGER REFERENCES messages(ROWID) ON DELETE CASCADE);
CREATE TABLE ews_copy_action_messages (ROWID INTEGER PRIMARY KEY, action INTEGER REFERENCES local_message_actions(ROWID) ON DELETE CASCADE, source_ews_item_id TEXT, source_message INTEGER REFERENCES messages(ROWID) ON DELETE SET NULL, destination_message INTEGER REFERENCES messages(ROWID) ON DELETE CASCADE);
CREATE TABLE mailbox_actions (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, account_identifier TEXT, action_type INTEGER, mailbox_name TEXT);
CREATE TABLE last_spotlight_check_date (message_id INTEGER NOT NULL UNIQUE ON CONFLICT REPLACE REFERENCES messages(ROWID) ON DELETE CASCADE, date INTEGER, PRIMARY KEY(message_id)) WITHOUT ROWID;
CREATE TABLE properties (ROWID INTEGER PRIMARY KEY, key, value, UNIQUE (key));
CREATE TABLE imap_labels (imap_message INTEGER REFERENCES imap_messages(ROWID) ON DELETE CASCADE, label INTEGER REFERENCES mailboxes(ROWID) ON DELETE CASCADE, PRIMARY KEY(imap_message, label)) WITHOUT ROWID;
CREATE INDEX date_index ON messages(date_received);
CREATE INDEX date_last_viewed_index ON messages(date_last_viewed);
CREATE INDEX date_created_index ON messages(date_created);
CREATE INDEX message_message_id_mailbox_index ON messages(message_id, mailbox);
CREATE INDEX message_document_id_index ON messages(document_id);
CREATE INDEX message_read_index ON messages(read);
CREATE INDEX message_flagged_index ON messages(flagged);
CREATE INDEX message_mailbox_index ON messages(mailbox, date_received);
CREATE INDEX message_remote_mailbox_index ON messages(remote_mailbox, remote_id);
CREATE INDEX message_type_index ON messages(type);
CREATE INDEX message_conversation_id_conversation_position_index ON messages(conversation_id, conversation_position);
CREATE INDEX message_fuzzy_ancestor_index ON messages(fuzzy_ancestor);
CREATE INDEX message_subject_fuzzy_ancestor_index ON messages(subject, fuzzy_ancestor);
CREATE INDEX message_sender_subject_automated_conversation_index ON messages(sender, subject, automated_conversation);
CREATE INDEX message_sender_index ON messages(sender);
CREATE INDEX message_root_status ON messages(root_status);
CREATE INDEX message_deleted_mailbox_index ON messages(deleted, mailbox);
CREATE INDEX message_deleted_index ON messages(deleted);
CREATE INDEX subject_subject_index ON subjects(subject);
CREATE INDEX subject_normalized_subject_index ON subjects(normalized_subject);
CREATE INDEX addresses_address_index ON addresses(address);
CREATE INDEX recipients_message_id_index ON recipients(message_id, position);
CREATE INDEX recipients_address_index ON recipients(address_id);
CREATE INDEX references_message_id_index ON threads(message_id);
CREATE INDEX references_reference_index ON threads(reference);
CREATE INDEX mailboxes_source_index ON mailboxes(source);
CREATE INDEX ews_folders_mailbox_id_index ON ews_folders(mailbox_id);
CREATE INDEX duplicates_unread_count_mailbox_id_index ON duplicates_unread_count(mailbox_id);
CREATE INDEX attachments_message_id_index ON attachments(message_id);
CREATE INDEX events_message_id_index ON events(message_id);
CREATE INDEX labels_mailbox_id_index on labels(mailbox_id);
CREATE UNIQUE INDEX imap_messages_mailbox_uid_index ON imap_messages(mailbox, uid);
CREATE INDEX imap_messages_message_index ON imap_messages(message);
CREATE INDEX local_message_actions_mailbox_index ON local_message_actions(mailbox);
CREATE INDEX action_imap_messages_action_index ON action_imap_messages(action);
CREATE INDEX action_ews_messages_action_index ON action_ews_messages(action);
CREATE INDEX action_messages_action_index ON action_messages(action);
CREATE INDEX action_messages_message_index ON action_messages(message);
CREATE INDEX action_labels_action_index ON action_labels(action);
CREATE INDEX action_labels_label_index ON action_labels(label);
CREATE INDEX imap_copy_action_messages_action_index ON imap_copy_action_messages(action);
CREATE INDEX imap_copy_action_messages_source_message_index ON imap_copy_action_messages(source_message);
CREATE INDEX imap_copy_action_messages_destination_message_index ON imap_copy_action_messages(destination_message);
CREATE INDEX ews_copy_action_messages_action_index ON ews_copy_action_messages(action);
CREATE INDEX ews_copy_action_messages_source_message_index ON ews_copy_action_messages(source_message);
CREATE INDEX ews_copy_action_messages_destination_message_index ON ews_copy_action_messages(destination_message);
CREATE INDEX mailbox_actions_action_type_index ON mailbox_actions(action_type);
CREATE INDEX last_spotlight_check_date_message_id_date_index ON last_spotlight_check_date(message_id, date);
CREATE TRIGGER before_delete_message BEFORE DELETE ON messages
BEGIN
UPDATE duplicates_unread_count SET unread_count = unread_count - 1 WHERE (OLD.message_id NOTNULL AND duplicates_unread_count.message_id = OLD.message_id AND duplicates_unread_count.mailbox_id = OLD.mailbox) AND (OLD.flags&1 = 0 AND OLD.flags&2 = 0);
UPDATE mailboxes SET unread_count_adjusted_for_duplicates = MAX(MIN(1, unread_count), unread_count_adjusted_for_duplicates - 1) WHERE ((mailboxes.ROWID = OLD.mailbox AND mailboxes.source ISNULL AND OLD.message_id ISNULL) OR (mailboxes.source NOTNULL AND mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = OLD.ROWID) AND ((mailboxes.source = OLD.mailbox AND OLD.message_id ISNULL) OR ((SELECT count() FROM labels WHERE message_id IN (SELECT ROWID FROM messages WHERE message_id = OLD.message_id) AND mailbox_id = mailboxes.ROWID) = 0 AND OLD.message_id NOTNULL)))) AND (OLD.flags&1 = 0 AND OLD.flags&2 = 0);

UPDATE mailboxes SET unread_count = MAX(0, unread_count - 1), unread_count_adjusted_for_duplicates = MIN(unread_count_adjusted_for_duplicates, unread_count - 1) WHERE ((mailboxes.ROWID = OLD.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = OLD.ROWID) AND mailboxes.source = OLD.mailbox)) AND (OLD.flags&1 = 0 AND OLD.flags&2 = 0);

UPDATE mailboxes SET total_count = MAX(0, total_count - 1) WHERE (mailboxes.ROWID = OLD.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = OLD.ROWID) AND mailboxes.source = OLD.mailbox);
UPDATE mailboxes SET unseen_count = MAX(0, unseen_count - 1) WHERE (mailboxes.ROWID = OLD.mailbox AND mailboxes.source ISNULL AND OLD.flags&1 = 0) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = OLD.ROWID) AND mailboxes.source = OLD.mailbox AND OLD.flags&1 = 0);
UPDATE mailboxes SET deleted_count = MAX(0, deleted_count - 1) WHERE (mailboxes.ROWID = OLD.mailbox AND mailboxes.source ISNULL AND OLD.flags&2 != 0) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = OLD.ROWID) AND mailboxes.source = OLD.mailbox AND OLD.flags&2 != 0);
END;
CREATE TRIGGER after_delete_message AFTER DELETE ON messages
BEGIN
DELETE FROM subjects WHERE ROWID = OLD.subject AND (SELECT COUNT() FROM messages WHERE subject = OLD.subject LIMIT 1) = 0;
DELETE FROM addresses WHERE ROWID = OLD.sender AND ((SELECT COUNT() FROM messages WHERE sender = OLD.sender LIMIT 1) = 0) AND ((SELECT COUNT() FROM recipients WHERE address_id = OLD.sender LIMIT 1) = 0);

UPDATE messages SET fuzzy_ancestor = -1 WHERE messages.fuzzy_ancestor = OLD.ROWID;
END;
CREATE TRIGGER after_insert_message AFTER INSERT ON messages
BEGIN
UPDATE mailboxes SET total_count = total_count + 1 WHERE (mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox);
UPDATE mailboxes SET unseen_count = unseen_count + 1 WHERE ((mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox)) AND NEW.flags&1 = 0;
UPDATE mailboxes SET deleted_count = deleted_count + 1 WHERE ((mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox)) AND NEW.flags&2 != 0;
END;
CREATE TRIGGER after_insert_message_unread AFTER INSERT ON messages WHEN (NEW.flags&1 = 0 AND NEW.flags&2 = 0)
BEGIN
UPDATE mailboxes SET unread_count = unread_count + 1 WHERE (mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox);

INSERT OR IGNORE INTO duplicates_unread_count (message_id, mailbox_id) VALUES (NEW.message_id, NEW.mailbox);
UPDATE duplicates_unread_count SET unread_count = unread_count + 1 WHERE NEW.message_id NOTNULL AND duplicates_unread_count.message_id = NEW.message_id AND duplicates_unread_count.mailbox_id = NEW.mailbox;
UPDATE mailboxes SET unread_count_adjusted_for_duplicates = MIN(unread_count_adjusted_for_duplicates + 1, unread_count) WHERE ((mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox)) AND NEW.message_id ISNULL;
END;
CREATE TRIGGER after_update_message AFTER UPDATE OF flags ON messages
BEGIN
UPDATE mailboxes SET unseen_count = MAX(0, unseen_count - 1) WHERE ((mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox)) AND OLD.flags&1 = 0 AND NEW.flags&1 != 0;
UPDATE mailboxes SET deleted_count = MAX(0, deleted_count - 1) WHERE ((mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox)) AND OLD.flags&2 != 0 AND NEW.flags&2 = 0;

UPDATE mailboxes SET unseen_count = unseen_count + 1 WHERE ((mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox)) AND OLD.flags&1 != 0 AND NEW.flags&1 = 0;
UPDATE mailboxes SET deleted_count = deleted_count + 1 WHERE ((mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox)) AND OLD.flags&2 = 0 AND NEW.flags&2 != 0;
END;
CREATE TRIGGER after_update_message_becoming_read AFTER UPDATE OF flags ON messages WHEN (OLD.flags&1 = 0 AND OLD.flags&2 = 0) AND (NEW.flags&1 != 0 OR NEW.flags&2 != 0)
BEGIN
UPDATE duplicates_unread_count SET unread_count = unread_count - 1 WHERE OLD.message_id NOTNULL AND duplicates_unread_count.message_id = OLD.message_id AND duplicates_unread_count.mailbox_id = OLD.mailbox;
UPDATE mailboxes SET unread_count_adjusted_for_duplicates = MAX(MIN(1, unread_count), unread_count_adjusted_for_duplicates - 1) WHERE ((mailboxes.ROWID = OLD.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = OLD.ROWID) AND mailboxes.source = OLD.mailbox)) AND OLD.message_id ISNULL;

UPDATE mailboxes SET unread_count = MAX(0, unread_count - 1), unread_count_adjusted_for_duplicates = MIN(unread_count_adjusted_for_duplicates, unread_count - 1) WHERE (mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox);
END;
CREATE TRIGGER after_update_message_becoming_unread AFTER UPDATE OF flags ON messages WHEN (OLD.flags&1 != 0 OR OLD.flags&2 != 0) AND (NEW.flags&1 = 0 AND NEW.flags&2 = 0)
BEGIN
UPDATE mailboxes SET unread_count = unread_count + 1 WHERE (mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox);

INSERT OR IGNORE INTO duplicates_unread_count (message_id, mailbox_id) VALUES (NEW.message_id, NEW.mailbox);
UPDATE duplicates_unread_count SET unread_count = unread_count + 1 WHERE NEW.message_id NOTNULL AND duplicates_unread_count.message_id = NEW.message_id AND duplicates_unread_count.mailbox_id = NEW.mailbox;
UPDATE mailboxes SET unread_count_adjusted_for_duplicates = MIN(unread_count_adjusted_for_duplicates + 1, unread_count) WHERE ((mailboxes.ROWID = NEW.mailbox AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id = NEW.ROWID) AND mailboxes.source = NEW.mailbox)) AND NEW.message_id ISNULL;
END;
CREATE TRIGGER after_update_duplicates_unread_count_becoming_unread AFTER UPDATE OF unread_count ON duplicates_unread_count WHEN OLD.unread_count = 0 AND NEW.unread_count = 1
BEGIN
UPDATE mailboxes SET unread_count_adjusted_for_duplicates = MIN(unread_count_adjusted_for_duplicates + 1, unread_count) WHERE (mailboxes.ROWID = NEW.mailbox_id AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id IN (SELECT ROWID FROM messages WHERE message_id = NEW.message_id AND mailbox = NEW.mailbox_id)) AND mailboxes.source = NEW.mailbox_id);
END;
CREATE TRIGGER after_update_duplicates_unread_count_becoming_read AFTER UPDATE OF unread_count ON duplicates_unread_count WHEN OLD.unread_count = 1 AND NEW.unread_count = 0
BEGIN
UPDATE mailboxes SET unread_count_adjusted_for_duplicates = MAX(MIN(1, unread_count), unread_count_adjusted_for_duplicates - 1) WHERE (mailboxes.ROWID = NEW.mailbox_id AND mailboxes.source ISNULL) OR (mailboxes.ROWID IN (SELECT mailbox_id FROM labels WHERE message_id IN (SELECT ROWID FROM messages WHERE message_id = NEW.message_id AND mailbox = NEW.mailbox_id)) AND mailboxes.source = NEW.mailbox_id);

DELETE FROM duplicates_unread_count WHERE rowid = NEW.rowid;
END;
CREATE TRIGGER after_insert_label AFTER INSERT ON labels
BEGIN
UPDATE mailboxes SET total_count = total_count + 1 WHERE mailboxes.ROWID = NEW.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = NEW.message_id LIMIT 1);
UPDATE mailboxes SET unseen_count = unseen_count + 1 WHERE mailboxes.ROWID = NEW.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = NEW.message_id AND flags&1 = 0 LIMIT 1);
UPDATE mailboxes SET deleted_count = deleted_count + 1 WHERE mailboxes.ROWID = NEW.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = NEW.message_id AND flags&2 != 0 LIMIT 1);
UPDATE mailboxes SET unread_count = unread_count + 1 WHERE mailboxes.ROWID = NEW.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = NEW.message_id AND flags&1 = 0 AND flags&2 = 0 LIMIT 1);
UPDATE mailboxes SET unread_count_adjusted_for_duplicates = MIN(unread_count_adjusted_for_duplicates + 1, unread_count) WHERE mailboxes.ROWID = NEW.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = NEW.message_id AND flags&1 = 0 AND flags&2 = 0 LIMIT 1) AND (SELECT count() FROM labels WHERE message_id IN (SELECT ROWID FROM messages WHERE message_id IN (SELECT message_id FROM messages WHERE ROWID = NEW.message_id) AND ROWID != NEW.message_id) AND mailbox_id = NEW.mailbox_id) = 0;
END;
CREATE TRIGGER after_delete_label AFTER DELETE ON labels
BEGIN
UPDATE mailboxes SET total_count = MAX(0, total_count - 1) WHERE mailboxes.ROWID = OLD.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = OLD.message_id LIMIT 1);
UPDATE mailboxes SET unseen_count = MAX(0, unseen_count - 1) WHERE mailboxes.ROWID = OLD.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = OLD.message_id AND flags&1 = 0 LIMIT 1);
UPDATE mailboxes SET deleted_count = MAX(0, deleted_count - 1) WHERE mailboxes.ROWID = OLD.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = OLD.message_id AND flags&2 != 0 LIMIT 1);
UPDATE mailboxes SET unread_count_adjusted_for_duplicates = MAX(MIN(1, unread_count), unread_count_adjusted_for_duplicates - 1) WHERE mailboxes.ROWID = OLD.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = OLD.message_id AND flags&1 = 0 AND flags&2 = 0 LIMIT 1) AND (SELECT count() FROM labels WHERE message_id IN (SELECT ROWID FROM messages WHERE message_id IN (SELECT message_id FROM messages WHERE ROWID = OLD.message_id) AND ROWID != OLD.message_id) AND mailbox_id = OLD.mailbox_id) = 0;
UPDATE mailboxes SET unread_count = MAX(0, unread_count - 1), unread_count_adjusted_for_duplicates = MIN(unread_count_adjusted_for_duplicates, unread_count - 1) WHERE mailboxes.ROWID = OLD.mailbox_id AND mailboxes.source IN (SELECT mailbox FROM messages WHERE ROWID = OLD.message_id AND flags&1 = 0 AND flags&2 = 0 LIMIT 1);
END;
```
