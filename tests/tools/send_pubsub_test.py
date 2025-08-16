import json
from datetime import datetime

from _dependencies.pubsub import Topics, publish_to_pubsub
from _dependencies.yandex_tools import _send_serialized_message

if __name__ == '__main__':
    message = [(276, None)]
    publish_to_pubsub(Topics.topic_to_run_parsing_script, message)
    pass
