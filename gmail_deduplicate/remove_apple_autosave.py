#!/usr/bin/env python3

"""
Apple mail saves backups.

Authorize your app here:
https://console.cloud.google.com/apis/dashboard
"""

CLIENT_SECRETS_FILE = 'client_secrets.json'
TOKEN_FILE='token_gmail.json'
SCOPES = ["https://mail.google.com/" ]

import os.path
import collections
from  collections import defaultdict,deque
import json
import time
import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest

import google.auth.exceptions


from ratelimit import limits, RateLimitException
from backoff import on_exception, expo

HTTP_ERRORS_MAX_RETRY = 4


def get_body(msg):
    # Extract the body
    body = ""
    if "parts" in msg["payload"]:
        for part in msg["payload"]["parts"]:
            if part["mimeType"] == "text/plain":
                body = part["body"]["data"]
                break
            elif part["mimeType"] == "text/html":
                body = part["body"]["data"]
                break
    else:
        body = msg["payload"]["body"]["data"]

    if body:
        import base64
        body = base64.urlsafe_b64decode(body).decode("utf-8")
    else:
        body = "No Body"


def delete_message(service, user_id, msg_id):
    try:
        service.users().messages().delete(userId=user_id, id=msg_id).execute()
        logging.info("Message with ID %s deleted successfully.",msg_id)
    except Exception as error:
        logging.error("An error occurred: %s",error)


"""
GMail Rate limits:
https://developers.google.com/gmail/api/reference/quota

messages.get - 5 quota units
messages.list - 5 quota units
gmail allows 250 quota units per second.

We will limit to 1 batch per second
Limit to 50 per batching documentation
5*45+5=230 which will be under the 250 quota units per second

However, this isn't always enough, so if we get a failure, we will skip a batch.
"""

LIST_MAX_RESULTS = 100
GET_BATCH_SIZE  = 30
RM_BATCH_SIZE   = 45

APPLE_AUTOSAVE_HEADER='X-Apple-Auto-Saved'

BAD_REQUEST_ERROR  = 400        # Google bug
TOO_MANY_REQUESTS_ERROR = 429
INTERNAL_SERVER_ERROR = 500
FORBIDDEN = 403

IGNORE_ERRORS_SET = set([BAD_REQUEST_ERROR, TOO_MANY_REQUESTS_ERROR, INTERNAL_SERVER_ERROR, FORBIDDEN])

def get_header(headers,name):
    return next((header['value'] for header in headers if header['name'] == name), None)

class RemoveAppleAutosave:
    def __init__(self, service):
        self.service = service
        self.extra_timeout = 0
        self.listed = 0
        self.get_message_ids = set() # messages we need to get
        self.del_messages    = deque() # messages we need to delete
        self.deleted = 0

    def batch_callback(self, request_id, response, exception):
        if exception:
            if exception.status_code in IGNORE_ERRORS_SET:
                self.extra_timeout += 1
                logging.info("EXTRA TIMEOUT")
                return
            logging.error("request_id=%s response=%s exception=(%s) %s",request_id,response,dir(exception),exception)
            raise RuntimeError(f"Unknown exception {exception.status_code} fetching messages: {exception}")
        self.listed += 1
        self.get_message_ids.remove( response['id'] )
        headers = response['payload']['headers']
        aas     = get_header(headers, APPLE_AUTOSAVE_HEADER)
        if aas:
            self.del_messages.append( response )

    def run(self):
        """Scan the Gmail archive (files not in INBOX) and look for those with the APPLE_AUTOSAVE_HEADER.
        Gmail does not allow searching by arbitrary headers, so we need to download and examine every message.
        """
        page_token = None
        first  = True
        http_errors_retry = 0

        while first or page_token or self.get_message_ids or self.del_messages:
            # see if we have more messages to get
            if (page_token is not None) or first:
                try:
                    messages = self.service.users().messages().list(userId="me",
                                                                    q='-label:INBOX',
                                                                    pageToken=page_token,
                                                                    maxResults=LIST_MAX_RESULTS).execute()
                    http_errors_retry = 0
                    messages_list = messages.get("messages", [])
                    for message in messages_list:
                        self.get_message_ids.add( message['id'] )
                        page_token = messages.get('nextPageToken')
                        first = False
                except HttpError as e:
                    logging.warning("HttpError on list: %s",e)
                    http_errors_retry += 1
                    if http_errors_retry>=HTTP_ERRORS_MAX_RETRY:
                        raise RuntimeError("HTTP Errors max retry") from e


            # see if we have any messageIds to process
            if self.get_message_ids:
                batch = self.service.new_batch_http_request(callback=self.batch_callback)
                for (ct,messageId) in enumerate(self.get_message_ids,1):
                    batch.add(self.service.users().messages().get(userId='me', id=messageId,
                                                             format='metadata',
                                                             metadataHeaders=['subject', 'date', 'to', APPLE_AUTOSAVE_HEADER]))
                    if ct>GET_BATCH_SIZE:
                        break
                try:
                    @on_exception(expo, RateLimitException, max_tries=16)
                    @limits(calls=1, period=1)
                    def call_api():
                        batch.execute()
                        if self.extra_timeout:
                            logging.info("  >> extra sleep %s",self.extra_timeout)
                            time.sleep(self.extra_timeout)
                            self.extra_timeout = 0
                    http_errors_retry = 0
                    call_api()
                except HttpError as e:
                    logging.warning("HttpError on batch: %s",e)
                    http_errors_retry += 1
                    if http_errors_retry>=HTTP_ERRORS_MAX_RETRY:
                        raise RuntimeError("HTTP Errors max retry") from e

            # see if we have any messages to delete
            to_del = []
            while len(to_del)<RM_BATCH_SIZE and self.del_messages:
                to_del.append(self.del_messages.pop())
            if to_del:
                ids = []
                for response in to_del:
                    headers = response['payload']['headers']
                    logging.info("delete %s %s",get_header(headers,'Date'),get_header(headers,'Subject'))
                    ids.append(response['id'])
                try:
                    self.service.users().messages().batchDelete(userId='me',body={'ids':ids}).execute()
                    self.deleted += len(ids)
                except HttpError as e:
                    logging.warning("Delete error: %s",e)
                    # Put back the failed added
                    for response in to_del:
                        self.del_messages.append(response)


            logging.info("files listed: %s deleted: %s",self.listed,self.deleted)


def get_creds():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except google.auth.exceptions.RefreshError:
                print("try deleting",TOKEN_FILE)
                exit(0)
        else:
            flow = InstalledAppFlow.from_client_secrets_file( CLIENT_SECRETS_FILE, SCOPES )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds

def main():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = get_creds()
    service = build("gmail", "v1", credentials=creds)

    r = RemoveAppleAutosave(service)
    r.run()


if __name__ == "__main__":
    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)
    try:
        main()
    except KeyboardInterrupt:
        print("Terminating.")
