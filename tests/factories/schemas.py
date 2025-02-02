from polyfactory.factories import DataclassFactory

from send_notifications.main import MessageToSend


class MessageFactory(DataclassFactory[MessageToSend]):
    message_params = '{"foo":1}'
    message_type = 'text'
