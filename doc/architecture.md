Here is a proposed architecture for our mail analysis system.

# Layer 1: Extraction and Ingesting
This layer may run within Autopsey directly, or it may be run from our stand-alone program. This layer:
1. Iterates through all mail messages in a folder/mailbox/ or an IMAP server.
2. Presents each email message to a function. 
3. The function extracts salienty features and stores them in a database.

Things to find out / decisions to make:
1. How much of this is currently done by Autopsey? 
2. Do we want to create our own ingest system that operates indpendent of Autospsy?
   a. Should our system be restartable -- meaning that it can be re-run and starts up from where it left off.
3. How should we keep our extracted data?
   a. Autopsy creates a full-text index. If we don't use Autospy, should we create our own? 
   b. If we use a database, should it be SQLite3, or MySQL, or Postgres, or should we have a database layer that abstracts that away?
   c. Should we use a NoSQL-style database?
  
# Layer 2: Analysis
# Layer 3: Visualization

Questions to be resolved:
1. Plain reports?
2. HTML/JavaScript interactive display?
