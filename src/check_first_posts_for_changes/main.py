"""Script does several things:
1. checks if the first posts of the searches were changed
2. checks active searches' status (Ищем, НЖ, НП, etc.)
3. checks active searches' visibility (accessible for everyone, restricted to a certain group or permanently deleted).
Updates are either saved in PSQL or send via pub/sub to other scripts"""

import os
import requests
import datetime
import re
import json
import logging
import difflib
import hashlib
import random

import sqlalchemy
# idea for optimization – to move to psycopg2

from google.cloud import secretmanager
from google.cloud import pubsub_v1


requests_session = requests.Session()
publisher = pubsub_v1.PublisherClient()

bad_gateway_counter = 0



def main(event, context): # noqa
    """main function"""

    global bad_gateway_counter
    bad_gateway_counter = 0


    print('914 line')
    """# BLOCK 1. for checking visibility (deleted or hidden) and status (Ищем, НЖ, НП) changes of active searches
    # A reason why this functionality – is in this script, is that it worth update the list of active searches first
    # and then check for first posts. Plus, once first posts checker finds something odd – it triggers a visibility
    # check for this search
    number_of_checked_searches = 100
    update_visibility_for_list_of_active_searches(number_of_checked_searches)"""

    # BLOCK 2. for checking if the first posts were changed
    # check is made for a certain % from the full list of active searches
    # below percent – is a matter of experiments: avoiding script timeout and minimize costs, but to get updates ASAP
    # percent_of_first_posts_to_check = 20
    # the chosen number of searches, for which first posts will be checked:
    # [first_posts] = [all_act_searches] * [percent]
    # then the [first_posts] is split by 5 subcategories, which has different % (sum of % should be 100)
    # so the check for first posts updates is happening
    # 1. start_time – will help to check only the latest searches with "freshest" starting time
    # 2. upd_time – will help to check only searches with the oldest previous update time
    # 3. folder_weight – will help to check only searches in the most popular regions
    # 4. checks_made – will help to check only searches with fewer previous checks
    # 5. random – turned out a good solution to check other searches that don't fall into prev categories
    """weights = {"start_time": 20, "upd_time": 20, "folder_weight": 20, "checks_made": 20, "random": 20}"""
    # update_first_posts_and_statuses()

    # if bad_gateway_counter > 3:
    #    publish_to_pubsub('topic_notify_admin', f'[che_posts]: Bad Gateway {bad_gateway_counter} times')

    # Close the open session
    

    return None
