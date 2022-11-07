import os

import psycopg2

import telegram
from telegram import ParseMode
from telegram import ReplyKeyboardMarkup

from google.cloud import secretmanager

project_id = None
client = None
db = None
cur = None
conn_psy = None
local_development = False
bot = None
bot_debug = None
admin_user_id = None


def sql_connect_by_psycopg2():
    global cur
    global conn_psy

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_host = '/cloudsql/' + db_conn

    conn_psy = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_pass)
    cur = conn_psy.cursor()


def get_secrets(secret_request):
    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    # noinspection PyUnresolvedReferences
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")


def set_basic_parameters():
    global project_id
    global client
    global cur
    global conn_psy
    global local_development
    global bot
    global bot_debug
    global admin_user_id

    # check if script is run locally or on cloud server
    if 'GCLOUD_PROJECT' in os.environ:
        local_development = False
    else:
        local_development = True

    if local_development is False:
        project_id = os.environ["GCP_PROJECT"]
        client = secretmanager.SecretManagerServiceClient()
        # bot_token = get_secrets("bot_api_token__prod")

        # initiate Prod Bot
        bot_token = get_secrets("bot_api_token__prod")
        bot = telegram.Bot(token=bot_token)

        # initiate Debug Bot
        bot_token_debug = get_secrets("bot_api_token")
        bot_debug = telegram.Bot(token=bot_token_debug)
        admin_user_id = get_secrets("my_telegram_id")

        sql_connect_by_psycopg2()

    else:
        pass


def main(event, context): # noqa
    global project_id  # can be deleted?
    global client  # can be deleted?
    global cur
    global conn_psy
    global local_development  # can be deleted?
    global bot

    set_basic_parameters()

    # download the news from SQL
    cur.execute("SELECT stage, text, status, id FROM news WHERE status is Null LIMIT 1;")
    conn_psy.commit()
    fetch = cur.fetchone()

    if fetch:
        news_from_sql = list(cur.fetchone())

        news_number = news_from_sql[3]
        news_text = news_from_sql[1]
        print(news_number)

        # download the list of users who gets the news
        cur.execute("select user_id from user_preferences WHERE preference = 'bot_news';")
        conn_psy.commit()
        list_of_users = [line[0] for line in cur.fetchall()]
        print(list_of_users)

        # prepare the keyboard
        button_1 = ['настроить регион поисков']
        button_2 = ['настроить "домашние координаты"']
        button_3 = ['настроить уведомления']
        button_4 = ['в начало']
        keyboard = [button_1, button_2, button_3, button_4]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # send the message:
        for user in list_of_users:
            try:

                # bot.sendMessage(user, news_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                bot.sendMessage(user, news_text, parse_mode=ParseMode.HTML)
                print('DBG.A.1.message_set_to_user:', user)

            except Exception as e:
                print('DBG.A.3.EXC:', repr(e))

        # set the news as published
        cur.execute("UPDATE news SET status='published' WHERE id=%s;", (news_number,))
    conn_psy.commit()

    conn_psy.close()

    return 'ok'
