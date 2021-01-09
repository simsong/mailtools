- [ ] Refactor the table of emails so that there is an abstract
  concept of 'person' that may have multiple email addresses and
  fullnames
- [ ] Modify Albert so that email addresses are presented with an
      object that separates out the email and the name.
- [ ] Create a recepients table that is a many-to-one binding to the
  messages table; remove rcpt_email from the messages table. it
  indexes into a specific email table
