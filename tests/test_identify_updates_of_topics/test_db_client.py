from datetime import datetime
from typing import TypeVar
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from identify_updates_of_topics._utils.database import DBClient
from identify_updates_of_topics._utils.topics_commons import (
    CoordType,
    ForumSearchItem,
)
from tests.common import find_model
from tests.factories import db_factories, db_models
from tests.test_identify_updates_of_topics.factories import (
    ChangeLogLineFactory,
    ForumCommentItemFactory,
    SearchSummaryFactory,
    fake,
)


class TestDBClient:
    def test_write_search(self, db_client: DBClient, session: Session):
        search_summary = SearchSummaryFactory.build()

        search_id = db_client.write_search(search_summary)

        search_model = find_model(session, db_models.Search, id=search_id)
        assert search_summary.topic_id == search_model.search_forum_num
        assert search_summary.parsed_time == search_model.parsed_time
        assert search_summary.title == search_model.forum_search_title
        assert search_summary.start_time == search_model.search_start_time
        assert search_summary.num_of_replies == search_model.num_of_replies
        assert search_summary.age == search_model.age
        assert search_summary.age_min == search_model.age_min
        assert search_summary.age_max == search_model.age_max
        assert search_summary.name == search_model.family_name
        assert search_summary.folder_id == search_model.forum_folder_id
        assert search_summary.topic_type == search_model.topic_type
        assert search_summary.display_name == search_model.display_name
        assert search_summary.new_status == search_model.status
        assert str(search_summary.locations) == search_model.city_locations
        assert search_summary.topic_type_id == search_model.topic_type_id

    def test_get_searches(self, db_client: DBClient):
        search = db_factories.SearchFactory.create_sync()

        searches = db_client.get_searches_by_ids([search.search_forum_num])

        assert search.search_forum_num in [x.topic_id for x in searches]

    def test_delete_search(self, db_client: DBClient, session: Session):
        search_to_delete, search_to_leave = db_factories.SearchFactory.create_batch_sync(2)

        db_client.delete_search(search_to_delete.search_forum_num)

        assert find_model(session, db_models.Search, id=search_to_leave.id)
        assert not find_model(session, db_models.Search, id=search_to_delete.id)

    def test_update_search_managers(self, db_client: DBClient, session: Session):
        search = db_factories.SearchFactory.create_sync()
        managers = ['foo', 'bar']

        db_client.update_search_managers(search.search_forum_num, managers)

        attr = find_model(session, db_models.SearchAttribute, search_forum_num=search.search_forum_num)
        assert attr.attribute_name == 'managers'
        assert attr.attribute_value == str(managers)

    def test_update_search_activities(self, db_client: DBClient, session: Session):
        search = db_factories.SearchFactory.create_sync()
        activities = ['foo']
        db_client.update_search_activities(search.search_forum_num, activities)

        attr = find_model(
            session, db_models.SearchActivity, search_forum_num=search.search_forum_num, activity_status='ongoing'
        )

        assert attr.activity_type == 'foo'

    def test_write_change_log(self, db_client: DBClient, session: Session):
        line = ChangeLogLineFactory.build()

        id_ = db_client.write_change_log(line)

        model = find_model(session, db_models.ChangeLog, id=id_)
        assert model.parsed_time == line.parsed_time
        assert model.search_forum_num == line.topic_id
        assert model.changed_field == line.changed_field
        assert model.new_value == line.new_value
        assert model.change_type == line.change_type

    def test_update_coordinates_in_db_already_existed(self, db_client: DBClient, session: Session):
        existed_coord = db_factories.SearchCoordinatesFactory.create_sync()
        search_id, lat, lon, coord_type = (
            existed_coord.search_id,
            fake.pyfloat(),
            fake.pyfloat(),
            CoordType.type_1_exact,
        )

        db_client.update_coordinates_in_db(search_id, lat, lon, coord_type)

        model = find_model(session, db_models.SearchCoordinate, search_id=search_id)
        assert model.coord_type == coord_type
        assert model.latitude == str(lat)
        assert model.longitude == str(lon)

    def test_update_coordinates_in_db_not_existed(self, db_client: DBClient, session: Session):
        search_id, lat, lon, coord_type = fake.pyint(), fake.pyfloat(), fake.pyfloat(), CoordType.type_1_exact

        db_client.update_coordinates_in_db(search_id, lat, lon, coord_type)

        model = find_model(session, db_models.SearchCoordinate, search_id=search_id)
        assert model.coord_type == coord_type
        assert model.latitude == str(lat)
        assert model.longitude == str(lon)

    def test_write_comment_ignored(self, db_client: DBClient, session: Session):
        comment = ForumCommentItemFactory.build(ignore=True)

        db_client.write_comment(comment)

        comment_model = find_model(session, db_models.Comment, search_forum_num=comment.search_num)
        assert comment_model.comment_text == comment.comment_text
        assert comment_model.notification_sent == 'n'
        assert comment_model.comment_global_num is None

    def test_write_comment_not_ignored(self, db_client: DBClient, session: Session):
        comment = ForumCommentItemFactory.build(ignore=False)

        db_client.write_comment(comment)

        comment_model = find_model(session, db_models.Comment, search_forum_num=comment.search_num)
        assert comment_model.comment_text == comment.comment_text
        assert comment_model.notification_sent is None
        assert comment_model.comment_global_num == comment.comment_forum_global_id

    def test_rewrite_snapshot_in_sql(self, db_client: DBClient, session: Session):
        folder_id = fake.pyint()
        snapshot_to_delete = db_factories.ForumSummarySnapshotFactory.create_sync(forum_folder_id=folder_id)
        snapshot_to_leave = db_factories.ForumSummarySnapshotFactory.create_sync()
        summaries = SearchSummaryFactory.batch(3, folder_id=folder_id)

        db_client.rewrite_snapshot_in_sql(folder_id, summaries)

        assert find_model(session, db_models.ForumSummarySnapshot, id=snapshot_to_leave.id)
        assert not find_model(session, db_models.ForumSummarySnapshot, id=snapshot_to_delete.id)

        new_snapshot = summaries[0]
        new_snapshot_model = find_model(
            session,
            db_models.ForumSummarySnapshot,
            forum_folder_id=new_snapshot.folder_id,
            search_forum_num=new_snapshot.topic_id,
        )
        assert new_snapshot.title == new_snapshot_model.forum_search_title

    def test_get_geolocation_form_psql_empty(self, db_client: DBClient, session: Session):
        res, *_ = db_client.get_geolocation_form_psql(fake.pystr())
        assert res is None

    def test_get_geolocation_form_psql(self, db_client: DBClient, session: Session):
        geocoding_model = db_factories.GeocodingFactory.create_sync(status='ok')

        status, lat, lon, geocoder = db_client.get_geolocation_form_psql(geocoding_model.address)

        assert status == 'ok'
        assert lat == geocoding_model.latitude
        assert lon == geocoding_model.longitude
        assert geocoder == geocoding_model.geocoder

    def test_save_place_in_psql(self, db_client: DBClient, session: Session):
        address = fake.address()
        search_num = fake.pyint()

        db_client.save_place_in_psql(address, search_num)

        result = find_model(session, db_models.SearchPlace, search_id=search_num, address=address)
        assert result is not None
        assert result.search_id == search_num
        assert result.address == address
        assert isinstance(result.timestamp, datetime)

    def test_get_key_value_item_empty(self, db_client: DBClient):
        key = fake.pystr()

        assert db_client.get_key_value_item(key) is None

    @pytest.mark.parametrize(
        'value',
        [
            None,
            'foo',
            {},
            {'foo': 'bar'},
            123,
            '',
        ],
    )
    def test_set_key_value_item(self, db_client: DBClient, value):
        key = fake.pystr()

        db_client.set_key_value_item(key, value)

        assert db_client.get_key_value_item(key) == value

    def test_set_key_value_item_twice(self, db_client: DBClient):
        key = fake.pystr()

        db_client.set_key_value_item(key, 1)
        db_client.set_key_value_item(key, 1)

    def test_delete_key_value_item(self, db_client: DBClient):
        key = fake.pystr()

        db_client.set_key_value_item(key, 1)

        assert db_client.get_key_value_item(key) == 1

        db_client.delete_key_value_item(key)

        assert db_client.get_key_value_item(key) is None

    def test_geocoder_cache(self, db_client: DBClient):
        address = fake.pystr(max_chars=50)
        db_client.save_geolocation_in_psql(address, 'fail', 50, 60, 'yandex')
        status, lat, lon, geocoder = db_client.get_geolocation_form_psql(address)

        assert geocoder == 'yandex'
