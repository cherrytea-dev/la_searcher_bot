import datetime
import os
import base64
import logging

from telegram import Bot

from google.cloud import secretmanager


def process_pubsub_message(event):
    """main entry function"""

    # receiving message text from pub/sub
    try:
        if 'data' in event:
            received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
            encoded_to_ascii = eval(received_message_from_pubsub)
            data_in_ascii = encoded_to_ascii['data']
            message_in_ascii = data_in_ascii['message']
        else:
            message_in_ascii = 'ERROR: I cannot read message from pub/sub'
    except: # noqa
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    return message_in_ascii


def main_func(event, context): # noqa

    message_from_pubsub = process_pubsub_message(event)
    logging.info(message_from_pubsub)

    logging.info('hello world')

    return None
