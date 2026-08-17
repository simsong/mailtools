import os
import json
from Contacts import CNContactStore, CNContact, CNMutableContact, CNContactFetchRequest
from Contacts import CNContactNoteKey, CNContactGivenNameKey, CNContactFamilyNameKey
from Foundation import NSMutableDictionary
from Foundation import NSObject
from Foundation import NSRunLoop
from Foundation import NSDate
from Foundation import NSDefaultRunLoopMode
from objc import super

class ContactAccessHandler(NSObject):
    def initWithCallback_(self, callback):
        self = super(ContactAccessHandler, self).init()
        if self is not None:
            self.callback = callback
        return self

    def handleAccess_error_(self, granted, error):
        self.callback(granted, error)

def deduplicate_lines(text):
    seen = set()
    result = []
    for line in text.splitlines():
        if line not in seen:
            seen.add(line)
            result.append(line)
    return "\n".join(result)

def deduplicate_comments():
    # Initialize the contact store
    store = CNContactStore()
    
    # Create a handler for the access request
    access_granted = [False]
    access_error = [None]
    
    def access_callback(granted, error):
        access_granted[0] = granted
        access_error[0] = error
    
    handler = ContactAccessHandler.alloc().initWithCallback_(access_callback)
    
    # Request access to contacts
    store.requestAccessForEntityType_completionHandler_(0, handler.handleAccess_error_)
    
    # Wait for the access request to complete
    while access_granted[0] is False and access_error[0] is None:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
    
    if not access_granted[0]:
        print("Access to contacts was denied")
        return
    
    # Create a fetch request
    fetch_request = CNContactFetchRequest.alloc().initWithKeysToFetch_([
        CNContactNoteKey,
        CNContactGivenNameKey,
        CNContactFamilyNameKey
    ])
    
    contacts = []
    updated_contacts = []
    
    # Get all contacts
    all_contacts = []
    store.enumerateContactsWithFetchRequest_error_usingBlock_(
        fetch_request,
        None,
        lambda contact, stop: all_contacts.append(contact)
    )
    
    for contact in all_contacts:
        name = f"{contact.givenName()} {contact.familyName()}".strip()
        if not name:
            name = "(No Name)"
        print("name:",name)    
        note = contact.note()
        if not note:
            continue
            
        original_value = note
        deduped_value = deduplicate_lines(original_value)
        
        contacts.append({
            'name': name,
            'comment': original_value
        })
        
        if original_value != deduped_value:
            print(f"Updating: {name}")
            updated_contacts.append({
                'name': name,
                'original_comment': original_value,
                'updated_comment': deduped_value
            })
            
            # Create a mutable copy of the contact
            mutable_contact = contact.mutableCopy()
            mutable_contact.setNote_(deduped_value)
            
            # Save the changes
            save_request = CNContactStore.alloc().init()
            save_request.saveContact_error_(mutable_contact, None)
    
    # Save the results to JSON files
    with open('original_contacts.json', 'w') as f:
        json.dump(contacts, f, indent=2)
    
    with open('updated_contacts.json', 'w') as f:
        json.dump(updated_contacts, f, indent=2)

if __name__ == '__main__':
    deduplicate_comments()
