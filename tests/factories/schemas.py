from polyfactory.factories import DataclassFactory

from send_notifications._utils.database import MessageToSend


class MessageFactory(DataclassFactory[MessageToSend]):
    message_params = '{"foo":1}'
    message_type = 'text'
