/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;


DROP TABLE IF EXISTS `subjects`;
CREATE TABLE subjects (
   rowid INTEGER PRIMARY KEY AUTO_INCREMENT,
   subject TEXT,
   normalized_subject TEXT,
   UNIQUE INDEX(subject(768)),
   FULLTEXT INDEX (subject),
   FULLTEXT INDEX (normalized_subject)
   );

DROP TABLE IF EXISTS `addresses`;
CREATE TABLE addresses (
   rowid INTEGER PRIMARY KEY AUTO_INCREMENT,
   address VARCHAR(255) COLLATE utf8_general_ci,
   comment VARCHAR(255) COLLATE utf8_general_ci,
   UNIQUE INDEX(address, comment)
);

DROP TABLE IF EXISTS `recipients`;
CREATE TABLE recipients (
    rowid INTEGER PRIMARY KEY AUTO_INCREMENT,
    message_id INTEGER NOT NULL,
    type INTEGER,
    address_id INTEGER NOT NULL,
    position INTEGER,
    FOREIGN KEY (message_id) REFERENCES messages(rowid) ON DELETE CASCADE,
    FOREIGN KEY (address_id) REFERENCES addresses(rowid) ON DELETE CASCADE
    );


DROP TABLE IF EXISTS `messages`;
CREATE TABLE messages (
       rowid INTEGER PRIMARY KEY AUTO_INCREMENT,
       message_id INTEGER,
       document_id BLOB,
       in_reply_to INTEGER,
       remote_id INTEGER,
       sender INTEGER,
       subject_prefix INTEGER,
       subject INTEGER,
       date_sent INTEGER,
       date_received INTEGER,
       date_created INTEGER,
       date_last_viewed INTEGER,
       mailbox INTEGER,
       remote_mailbox INTEGER,
       flags INTEGER,
       flagged INTEGER,
       bytes INTEGER,
       conversation_id INTEGER DEFAULT -1,
       snippet TEXT DEFAULT NULL,
       fuzzy_ancestor INTEGER DEFAULT NULL,
       automated_conversation INTEGER DEFAULT 0,
       root_status INTEGER DEFAULT -1,
       conversation_position INTEGER DEFAULT -1,
       deleted INTEGER DEFAULT 0,
       FOREIGN KEY (sender) REFERENCES addresses(rowid),
       FOREIGN KEY (subject) REFERENCES subjects(rowid)
       );


DROP TABLE IF EXISTS `keywords`;
CREATE TABLE keywords (
       rowid INTEGER PRIMARY KEY AUTO_INCREMENT,
       keyword TEXT,
       FULLTEXT INDEX (keyword)
       );

DROP TABLE IF EXISTS `message_keywords`;
CREATE TABLE message_keywords (
       keyword_id INTEGER NOT NULL,
       message_id INTEGER NOT NULL,
       UNIQUE INDEX (keyword_id, message_id),
       UNIQUE INDEX (message_id, keyword_id)
       );

DROP TABLE IF EXISTS `message_text`;
CREATE TABLE message_text (
       message_id INTEGER PRIMARY KEY AUTO_INCREMENT,
       full_text TEXT NOT NULL,
       FULLTEXT INDEX (full_text)
       );




/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
