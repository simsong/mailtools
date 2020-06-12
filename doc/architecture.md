Here is a proposed architecture for our mail analysis system.

# Overall Design
* [Diagram](https://app.diagrams.net/?lightbox=1&highlight=0000ff&edit=_blank&layers=1&nav=1&title=Layers.draw#R1Zhbb5swGIZ%2FTS5XYQw0vWwO3Sa1arVI23o1OeCCNQcjYxror9%2FnYs50yaocupvI34v92Tx%2BfSATPN%2FknyVJojsRUD6xrSCf4MXEtvGlC79aKErBcZ1SCCULSgk1woq9UCNaRs1YQNNORSUEVyzpir6IY%2BqrjkakFNtutSfBu70mJKQDYeUTPlR%2FsEBFpTp1rUb%2FQlkYVT0jyzzZkKqyEdKIBGLbkvBygudSCFWWNvmccs2u4lK2u3njaT0wSWO1TwN7Lq%2F418xh8bf4Zplkv%2B7X6JNdZnkmPDMvvMyVJL5iIgb9lhRUmuGromIiRRYHVKe1Jni2jZiiq4T4%2BukWTABapDYcIgRF0wGViuZvjhzVPMBHVGyokgVUMQ2mhqCxkFsh3jYTgjyjRa3JqDRiPBDWmRtMUDCk%2FoEaHlC7IwxaeRx6nq2BmBfq0koJSQf4wAiJLvoFZ8BR7ma4LoHfrmuB%2BL%2FD12m4zxRkoYeDjXCXtjdCewz29FiwnQHs65jwImXpRzVoHZ%2FNoO7fmC1m%2F7kl8Qjfk1rSG%2BB9k%2BgTp%2Fm1PocABY0DU1z4nKQp88ecSIPBidQDBR2JTPp09w6liAyp2rX%2FD8G3wLojYCtNUk4Ue%2B4Od4y26eFBMHiRel6x19vYUW%2FCytc0rdpHWy%2BRg7qJnP7CKjkMEr1Ofv3a7%2FfD5XH8QHOmfupN7MI10aPZ0nR5kbeDwgQH9JC7p4ecc3oI9TyEnXd6CF32zIj38xDMICla1RJdIT2Gy6ZHclkMw2rZTIeP7WeN0V6jomW7M7rT3tOd7jndafdM5bzbnW4vUX%2BrPPIOV3XXMt93lmaEsxdSfiv0nAg54RMNgll9t%2BAiC05yHau%2FwQws5Izcx%2BxTXhgQ%2BjgnRHu9I9xe8dbFlYd3rXodPVDJAIy%2BJx56WTt7LmtkjVvgRKdOb13jqwOdOtg93akDYfPvQ1m9%2BQsHL%2F8A)


## System Architecture Principles
Where possible, the system will subscribe to these principles:

* [composability](https://en.wikipedia.org/wiki/Composability) - Any
  layer can work with any other layer.
* [Idempotence](https://en.wikipedia.org/wiki/Idempotence) - Any module can be run multiple times without additional side-effects.
* [Modularity](https://en.wikipedia.org/wiki/Modularity) - The system is divided into modules, each one accomplishing one particular purpose.

## Layers
The system implements these three layers:

**Data Extraction Layer** - Extracts information from an arbitrary mail archive and stores it in a data store. 

Exmaples of mail archives include:

* Outlook PST
* MBOX file
* Gmail
* Remote IMAP server

Examples of databases include:

* PostgreSQL
* SQLite3
* MySQL
* MongoDB

Realistically, we only want to support a single database. SQL databases have a lot of history and we can use a subset of SQL that will run on SQLite3 and MySQL, so we will do that using the [ctools.dbfile](https://github.com/simsong/ctools/blob/master/dbfile.py) class.


**Data Analysis Layer** - Reads the contents of the database and performs multiple analyses. Ideally any data analysis could work with any database provided that it uses the same schema. In practice, Analysis tends to be linked to the data representaiton and to the data presentation.


**Data Presentation Layer** - Visualizes the information found in the data analysis layer. 

**Driver Program and Deployment Layer** - This layer assembles a specific combianton of components in the previous layers. 

## Development process
Given the above layers, development might go like this:

1. Create a Data Extractor for a specific mail archive.
2. Create a Database connector that just prints message metadata instead of storing it.
3. Test the Extractor with the Printer on a small set of mail messages and verify that the output is correct.
4. Create a database layer that stores the messages in the database
5. Test the Extractor with the database storage layer and verify the contents of the databsae.
6. Create a simple analysis program that extracts a specific kind of metadata (e.g. From and Subject lines)
7. Create a visualization that does text output for the analysis program.
8. Test the analysis program to make sure that its output is correct.
9. Create a new visualization that draws something on the screen.
10. Create a visualization-to-text layer that reads what's on the screen and turns it into text.
11. Test the visualization layer to determine that the text output matches what is expected from the email messages.


## Implementation and Integration Plans

1. Adopt a *strict subset* of Apple's mailbox schema as our schema.
	* It's evolved and well-thought-out, although it is a little comlex.
	* Allows immediate analysis of databases from mac desktops and iPhones
	* Will need to be modified for MySQL, which most easily done by simplifying it.

2. People who are interested in learning can experiment in their own module, without impacting the main system (provides more flexibility than Git branches.)

3. Implement Extraction and Analysis in Python, Visualization in JavaScript.
   * There are much better JavaScript visualization tools.
   * Allows for deployment in a web browser.
   * There are good technologies for running web apps from Python.
   * Web app can run locally or remotely.



  

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
