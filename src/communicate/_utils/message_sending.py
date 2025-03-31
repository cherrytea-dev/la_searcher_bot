import asyncio
import json
import logging
import urllib.request
from typing import Union

import requests
from requests.models import Response
from telegram import TelegramObject
from telegram.ext import Application, ContextTypes

from _dependencies.commons import Topics, get_app_config, publish_to_pubsub
from _dependencies.misc import notify_admin


async def leave_chat_async(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.leave_chat(chat_id=context.job.chat_id)


async def prepare_message_for_leave_chat_async(user_id):
    # TODO DOUBLE
    bot_token = get_app_config().bot_api_token__prod
    application = Application.builder().token(bot_token).build()
    job_queue = application.job_queue
    job_queue.run_once(leave_chat_async, 0, chat_id=user_id)

    async with application:
        await application.initialize()
        await application.start()
        await application.stop()
        await application.shutdown()

    return 'ok'


def process_response_of_api_call(user_id: int, response: Response, call_context: str = '') -> str:
    """process response received as a result of Telegram API call while sending message/location"""

    try:
        if 'ok' not in response.json():
            notify_admin(f'ALARM! "ok" is not in response: {response.json()}, user {user_id}')
            return 'failed'

        if response.ok:
            logging.info(f'message to {user_id} was successfully sent')
            return 'completed'

        elif response.status_code == 400:  # Bad Request
            logging.exception(f'Bad Request: message to {user_id} was not sent, {response.json()=}')
            return 'cancelled_bad_request'

        elif response.status_code == 403:  # FORBIDDEN
            logging.info(f'Forbidden: message to {user_id} was not sent, {response.reason=}')
            action = None
            if response.text.find('bot was blocked by the user') != -1:
                action = 'block_user'
            if response.text.find('user is deactivated') != -1:
                action = 'delete_user'
            if action:
                message_for_pubsub = {'action': action, 'info': {'user': user_id}}
                publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)
                logging.info(f'Identified user id {user_id} to do {action}')
            return 'cancelled'

        elif 420 <= response.status_code <= 429:  # 'Flood Control':
            logging.exception(f'Flood Control: message to {user_id} was not sent, {response.reason=}')
            return 'failed_flood_control'

        # issue425 if not response moved here from the 1st place because it reacted even on response 400
        elif not response:
            logging.info(f'response is None for {user_id=}; {call_context=}')
            return 'failed'

        else:
            logging.exception(f'UNKNOWN ERROR: message to {user_id} was not sent, {response.reason=}')
            return 'cancelled'

    except Exception as e:
        logging.exception(f'Response is corrupted. {response.json()=}')
        return 'failed'


def process_leaving_chat_async(user_id) -> None:
    asyncio.run(prepare_message_for_leave_chat_async(user_id))


def send_message_to_api(bot_token, user_id, message, params):
    """send message directly to Telegram API w/o any wrappers ar libraries"""

    try:
        parse_mode = ''
        disable_web_page_preview = ''
        reply_markup = ''
        if params:
            if 'parse_mode' in params.keys():
                parse_mode = f'&parse_mode={params["parse_mode"]}'
            if 'disable_web_page_preview' in params.keys():
                disable_web_page_preview = f'&disable_web_page_preview={params["disable_web_page_preview"]}'
            if 'reply_markup' in params.keys():
                rep_as_str = str(json.dumps(params['reply_markup']))
                reply_markup = f'&reply_markup={urllib.parse.quote(rep_as_str)}'
        message_encoded = f'&text={urllib.parse.quote(message)}'

        request_text = (
            f'https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={user_id}'
            f'{message_encoded}{parse_mode}{disable_web_page_preview}{reply_markup}'
        )

        with requests.Session() as session:
            response = session.get(request_text)
            logging.info(str(response))

    except Exception as e:
        logging.exception('Error in getting response from Telegram')
        response = None

    result = process_response_of_api_call(user_id, response)

    return result


def send_callback_answer_to_api(bot_token: str, callback_query_id: str, message: str) -> str:
    """send a notification when inline button is pushed directly to Telegram API w/o any wrappers ar libraries"""

    try:
        # NB! only 200 characters
        message = message[:200]
        message_encoded = f'&text={urllib.parse.quote(message)}'

        request_text = (
            f'https://api.telegram.org/bot{bot_token}/answerCallbackQuery?callback_query_id='
            f'{callback_query_id}{message_encoded}'
        )

        with requests.Session() as session:
            response = session.get(request_text)
            logging.info(f'send_callback_answer_to_api..{response.json()=}')

    except Exception as e:
        logging.exception('Error in getting response from Telegram')
        response = None

    result = process_response_of_api_call(callback_query_id, response)

    return result


def make_api_call(method: str, bot_api_token: str, params: dict, call_context='') -> Union[requests.Response, None]:
    """make an API call to telegram"""

    if not params or not bot_api_token or not method:
        logging.warning(
            f'not params or not bot_api_token or not method: {method=}; {len(bot_api_token)=}; {len(params)=}'
        )
        return None

    if 'chat_id' not in params.keys() and ('scope' not in params.keys() or 'chat_id' not in params['scope'].keys()):
        return None

    url = f'https://api.telegram.org/bot{bot_api_token}/{method}'  # e.g. sendMessage
    headers = {'Content-Type': 'application/json'}

    if 'reply_markup' in params and isinstance(params['reply_markup'], TelegramObject):
        params['reply_markup'] = params['reply_markup'].to_dict()
    logging.info(f'({method=}, {call_context=})..before json_params = json.dumps(params) {params=}; {type(params)=}')
    json_params = json.dumps(params)
    logging.info(f'({method=}, {call_context=})..after json.dumps(params): {json_params=}; {type(json_params)=}')

    with requests.Session() as session:
        try:
            response = session.post(url=url, data=json_params, headers=headers)
            logging.info(f'After session.post: {response=}; {call_context=}')
        except Exception as e:
            response = None
            logging.exception('Error in getting response from Telegram')

    logging.info(f'Before return: {response=}; {call_context=}')
    return response


def api_callback_edit_inline_keyboard(bot_token: str, callback_query: dict, reply_markup: dict, user_id: str) -> str:
    """send a notification when inline button is pushed directly to Telegram API w/o any wrappers ar libraries"""
    if reply_markup and not isinstance(reply_markup, dict):
        reply_markup_dict = reply_markup.to_dict()

    params = {
        'chat_id': callback_query['message']['chat']['id'],
        'message_id': callback_query['message']['message_id'],
        'text': callback_query['message']['text'],
        'reply_markup': reply_markup_dict,
    }

    response = make_api_call('editMessageText', bot_token, params, 'api_callback_edit_inline_keyboard')
    logging.info(f'After make_api_call(editMessageText): {response.json()=}')
    result = process_response_of_api_call(user_id, response)
    return result
