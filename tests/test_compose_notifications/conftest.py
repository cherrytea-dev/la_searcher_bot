from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from _dependencies.commons import ChangeType, TopicType
from tests.factories import db_factories, db_models


@pytest.fixture(autouse=True)
def local_patches():
    with (
        patch('compose_notifications.main.publish_to_pubsub'),
        patch('compose_notifications._utils.notifications_maker.publish_to_pubsub'),
    ):
        yield


@pytest.fixture(scope='session')
def dict_notif_type_status_change() -> db_models.DictNotifType:
    # TODO generate all types
    with db_factories.get_session() as session:
        return get_or_create_dict_notif_type(session, ChangeType.topic_status_change)


@pytest.fixture(scope='session')
def dict_notif_type_new() -> db_models.DictNotifType:
    # TODO generate all types
    with db_factories.get_session() as session:
        return get_or_create_dict_notif_type(session, ChangeType.topic_new)


@pytest.fixture(scope='session')
def dict_notif_type_first_post_change() -> db_models.DictNotifType:
    # TODO generate all types
    with db_factories.get_session() as session:
        return get_or_create_dict_notif_type(session, ChangeType.topic_first_post_change)


def get_or_create_dict_notif_type(session: Session, type_id: ChangeType) -> db_models.DictNotifType:
    instance = session.query(db_models.DictNotifType).filter_by(type_id=type_id).first()
    if instance:
        return instance
    else:
        instance = db_models.DictNotifType(type_id=type_id.value, type_name=type_id.name)
        session.add(instance)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            instance = session.query(db_models.DictNotifType).filter_by(type_id=type_id).first()
        return instance
