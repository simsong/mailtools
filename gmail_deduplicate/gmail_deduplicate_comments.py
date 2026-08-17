import os
import json
from Contacts import CNContactStore, CNContact, CNMutableContact
from Contacts import CNContactNoteKey, CNContactGivenNameKey, CNContactFamilyNameKey
from Foundation import NSMutableDictionary

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
    
    # Request access to contacts
    store.requestAccessForEntityType_completionHandler_(0, None)  # 0 is for contacts
    
    # Fetch all contacts
    fetch_request = CNContact.alloc().init()
    fetch_request.setKeysToFetch_([CNContactNoteKey, CNContactGivenNameKey, CNContactFamilyNameKey])
    
    contacts = []
    updated_contacts = []
    
    # Get all contacts
    all_contacts = store.unifiedContactsMatchingPredicate_keysToFetch_error_(
        None,  # predicate to match all contacts
        [CNContactNoteKey, CNContactGivenNameKey, CNContactFamilyNameKey],
        None
    )
    
    for contact in all_contacts:
        name = f"{contact.givenName()} {contact.familyName()}".strip()
        if not name:
            name = "(No Name)"
            
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
