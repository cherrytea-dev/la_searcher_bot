import datetime
import os
import base64
import logging

from telegram import Bot

from google.cloud import secretmanager


project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()


def get_secrets(secret_request):
    """get google cloud secret"""

    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def process_pubsub_message(event):
    """get the text message from pubsub"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
        encoded_to_ascii = eval(received_message_from_pubsub)
        data_in_ascii = encoded_to_ascii['data']
        message_in_ascii = data_in_ascii['message']
    else:
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    return message_in_ascii


def send_message(admin_user_id, message, bot):
    """send individual notification message to telegram (debug)"""

    # TODO: DEBUG
    # logger_for_send_message = logging.getLogger('sendMessage')
    # logger_for_send_message.setLevel()
    # TODO: DEBUG

    try:

        # to avoid 4000 symbols restriction for telegram message
        if len(message) > 3500:
            message = message[:1500]

        bot.sendMessage(chat_id=admin_user_id, text=message)

    except Exception as e:
        logging.info('[send_debug]: send debug to telegram failed')
        logging.exception(e)

        try:
            # for rare case:
            # "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
            # TODO: if it continues – reason should be clarified and mitigated

            debug_message = 'ERROR! ' + str(datetime.datetime.now()) + ': ' + str(e)
            bot.sendMessage(chat_id=admin_user_id, text=debug_message)

        except: # noqa
            pass

    return None


def main(event, context): # noqa
    """main function, envoked by pub/sub, which sends the notification to Admin""" # noqa

    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    logging.info('[sand_debug]: received from pubsub: {}'.format(pubsub_message)) # noqa

    message_from_pubsub = process_pubsub_message(event)

    admin_user_id = get_secrets("my_telegram_id")
    bot_token_debug = get_secrets("bot_api_token")

    bot = Bot(token=bot_token_debug)

    send_message(admin_user_id, message_from_pubsub, bot)

    return None
