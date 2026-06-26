from _dependencies.common.pubsub import Topics, publish_to_pubsub

if __name__ == '__main__':
    message = [(276, None)]
    publish_to_pubsub(Topics.topic_to_run_parsing_script, message)
    pass
