# coding: utf-8
from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()
metadata = Base.metadata


class ChangeLog(Base):
    __tablename__ = 'change_log'

    id = Column(Integer, primary_key=True, server_default=text("nextval('change_log_id_seq1'::regclass)"))
    parsed_time = Column(DateTime)
    search_forum_num = Column(Integer)
    changed_field = Column(String(255))
    new_value = Column(String)
    notification_sent = Column(String(3))
    parameters = Column(String)
    notif_sent_staging = Column(String(1))
    change_type = Column(Integer)


class Comment(Base):
    __tablename__ = 'comments'

    id = Column(Integer, primary_key=True, server_default=text("nextval('comments_id_seq1'::regclass)"))
    comment_url = Column(String)
    comment_text = Column(String)
    comment_author_nickname = Column(String)
    comment_author_link = Column(String)
    search_forum_num = Column(Integer)
    comment_num = Column(Integer)
    comment_global_num = Column(String(10))
    notification_sent = Column(String(1))
    notif_sent_staging = Column(String(1))
    notif_sent_inforg = Column(String(1))


t_communications_last_inline_msg = Table(
    'communications_last_inline_msg',
    metadata,
    Column(
        'id',
        Integer,
        nullable=False,
        server_default=text("nextval('communications_last_inline_msg_id_seq1'::regclass)"),
    ),
    Column('user_id', BigInteger, nullable=False),
    Column('timestamp', DateTime(True)),
    Column('message_id', BigInteger),
    UniqueConstraint('user_id', 'message_id'),
)


class Dialog(Base):
    __tablename__ = 'dialogs'

    id = Column(Integer, primary_key=True, server_default=text("nextval('dialogs_id_seq1'::regclass)"))
    timestamp = Column(DateTime)
    user_id = Column(BigInteger)
    author = Column(String(10))
    message_id = Column(BigInteger)
    message_text = Column(String)


class DictNotifType(Base):
    __tablename__ = 'dict_notif_types'

    type_id = Column(Integer, primary_key=True)
    type_name = Column(String(100), nullable=False)


class DictSearchActivity(Base):
    __tablename__ = 'dict_search_activities'

    id = Column(Integer, primary_key=True, server_default=text("nextval('dict_search_activities_id_seq1'::regclass)"))
    activity_id = Column(String)
    activity_name = Column(String)


class DictTopicType(Base):
    __tablename__ = 'dict_topic_types'

    id = Column(Integer, primary_key=True)
    topic_type_name = Column(String(20))


class Feedback(Base):
    __tablename__ = 'feedback'

    id = Column(Integer, primary_key=True, server_default=text("nextval('feedback_id_seq1'::regclass)"))
    username = Column(String)
    feedback_text = Column(String)
    feedback_time = Column(DateTime)
    user_id = Column(String)
    message_id = Column(Integer)


class ForumSummarySnapshot(Base):
    __tablename__ = 'forum_summary_snapshot'

    search_forum_num = Column(Integer)
    parsed_time = Column(DateTime)
    status_short = Column(String)
    forum_search_title = Column(String)
    cut_link = Column(String)
    search_start_time = Column(DateTime)
    num_of_replies = Column(Integer)
    family_name = Column(String)
    age = Column(Integer)
    id = Column(Integer, primary_key=True, server_default=text("nextval('forum_summary_snapshot_id_seq1'::regclass)"))
    forum_folder_id = Column(Integer)
    topic_type = Column(String(30))
    display_name = Column(String(100))
    age_min = Column(Integer)
    age_max = Column(Integer)
    status = Column(String(20))
    locations = Column(String)
    city_locations = Column(String)
    topic_type_id = Column(Integer)


class FunctionsRegistry(Base):
    __tablename__ = 'functions_registry'

    id = Column(Integer, primary_key=True, server_default=text("nextval('functions_registry_id_seq'::regclass)"))
    time_start = Column(DateTime)
    time_finish = Column(DateTime)
    event_id = Column(BigInteger)
    cloud_function_name = Column(String(30))
    params = Column(JSON)
    triggered_by = Column(BigInteger)
    function_id = Column(BigInteger)
    triggered_by_func_id = Column(BigInteger)


class GeoDivision(Base):
    __tablename__ = 'geo_divisions'

    division_id = Column(Integer, primary_key=True)
    division_name = Column(String(40))


class GeoFolder(Base):
    __tablename__ = 'geo_folders'

    folder_id = Column(Integer, primary_key=True)
    division_id = Column(Integer)
    folder_type = Column(String(12))
    folder_subtype = Column(String(26))


t_geo_folders_view = Table(
    'geo_folders_view',
    metadata,
    Column('folder_id', Integer),
    Column('division_id', Integer),
    Column('division_name', String(40)),
    Column('folder_type', String(12)),
    Column('folder_subtype', String(26)),
    Column('folder_display_name', String),
)


class GeoRegion(Base):
    __tablename__ = 'geo_regions'

    region_id = Column(String(6), primary_key=True)
    division_id = Column(Integer)
    polygon_id = Column(Integer)
    name_full = Column(String(100))
    name_short = Column(String(30))
    federal_district = Column(String(17))


class GeocodeLastApiCall(Base):
    __tablename__ = 'geocode_last_api_call'

    id = Column(Integer, primary_key=True, server_default=text("nextval('geocode_last_api_call_id_seq1'::regclass)"))
    geocoder = Column(String(20))
    timestamp = Column(DateTime(True))


class Geocoding(Base):
    __tablename__ = 'geocoding'

    id = Column(Integer, primary_key=True, server_default=text("nextval('geocoding_id_seq1'::regclass)"))
    address = Column(String, unique=True)
    status = Column(String)
    latitude = Column(Float(53))
    longitude = Column(Float(53))
    geocoder = Column(String(10))
    timestamp = Column(DateTime(True))


t_key_value_storage = Table(
    'key_value_storage',
    metadata,
    Column('key', String(100), nullable=False, unique=True),
    Column('value', JSONB(astext_type=Text())),
)


class MsgFromBot(Base):
    __tablename__ = 'msg_from_bot'

    id = Column(Integer, primary_key=True, server_default=text("nextval('msg_from_bot_id_seq1'::regclass)"))
    time = Column(DateTime)
    msg_type = Column(String)
    msg_text = Column(String)
    user_id = Column(BigInteger)


class News(Base):
    __tablename__ = 'news'

    id = Column(Integer, primary_key=True, server_default=text("nextval('news_id_seq1'::regclass)"))
    stage = Column(String)
    text = Column(String)
    status = Column(String)


t_notif_by_user__history = Table(
    'notif_by_user__history',
    metadata,
    Column('message_id', BigInteger),
    Column('mailing_id', Integer),
    Column('user_id', BigInteger),
    Column('message_content', String),
    Column('message_text', String),
    Column('message_type', String(50)),
    Column('message_params', String),
    Column('message_group_id', Integer),
    Column('change_log_id', Integer),
    Column('created', DateTime),
    Column('completed', DateTime),
    Column('cancelled', DateTime),
    Column('failed', DateTime),
    Column('num_of_fails', Integer),
)


class NotifByUserStatu(Base):
    __tablename__ = 'notif_by_user_status'

    id = Column(BigInteger, primary_key=True, server_default=text("nextval('notif_by_user_status_id_seq1'::regclass)"))
    message_id = Column(BigInteger)
    event = Column(String(100), nullable=False)
    event_timestamp = Column(DateTime, nullable=False)
    context = Column(String)
    mailing_id = Column(Integer)
    change_log_id = Column(Integer)
    user_id = Column(BigInteger)
    message_type = Column(String(50))


t_notif_by_user_status__history = Table(
    'notif_by_user_status__history',
    metadata,
    Column('id', BigInteger),
    Column('message_id', BigInteger),
    Column('event', String(100)),
    Column('event_timestamp', DateTime),
    Column('context', String),
    Column('mailing_id', Integer),
    Column('change_log_id', Integer),
    Column('user_id', BigInteger),
    Column('message_type', String(50)),
)


class NotifStatSendingSpeed(Base):
    __tablename__ = 'notif_stat_sending_speed'

    id = Column(Integer, primary_key=True, server_default=text("nextval('notif_stat_sending_speed_id_seq1'::regclass)"))
    timestamp = Column(DateTime)
    num_of_msgs = Column(Integer)
    speed = Column(Float)
    ttl_time = Column(Float)


t_old_dict_regions = Table(
    'old_dict_regions',
    metadata,
    Column('id', Integer, nullable=False, server_default=text("nextval('my_serial'::regclass)")),
    Column('region_name', String),
)


t_old_folders = Table(
    'old_folders',
    metadata,
    Column('folder_id', Integer),
    Column('folder_name', String(255)),
    Column('folder_type', String(100)),
    Column('region', String(255)),
    Column('region_id', Integer),
)


class OldRegion(Base):
    __tablename__ = 'old_regions'

    id = Column(Integer, primary_key=True, server_default=text("nextval('regions_id_seq'::regclass)"))
    region_name = Column(String)
    yandex_reg_id = Column(ARRAY(Integer()))


class OldRegionsToFolder(Base):
    __tablename__ = 'old_regions_to_folders'

    id = Column(Integer, primary_key=True, server_default=text("nextval('regions_to_folders_id_seq'::regclass)"))
    forum_folder_id = Column(Integer)
    region_id = Column(Integer)
    folder_description = Column(String)


class ParsedSnapshot(Base):
    __tablename__ = 'parsed_snapshot'

    search_forum_num = Column(Integer)
    parsed_time = Column(DateTime)
    status_short = Column(String(255))
    forum_search_title = Column(String(255))
    cut_link = Column(String(255))
    search_start_time = Column(DateTime)
    num_of_replies = Column(Integer)
    entry_id = Column(
        Integer, primary_key=True, server_default=text("nextval('parsed_snapshot_entry_id_seq1'::regclass)")
    )
    search_person_age = Column(Integer)
    name = Column(String)
    forum_folder_id = Column(Integer)


class PrevSnapshot(Base):
    __tablename__ = 'prev_snapshot'

    hash = Column(String)
    id = Column(Integer, primary_key=True, server_default=text("nextval('prev_snapshot_id_seq1'::regclass)"))


class SearchActivity(Base):
    __tablename__ = 'search_activities'

    id = Column(Integer, primary_key=True, server_default=text("nextval('search_activities_id_seq2'::regclass)"))
    search_forum_num = Column(Integer)
    activity_type = Column(String)
    activity_parameters = Column(String)
    activity_status = Column(String)
    timestamp = Column(DateTime)


class SearchAttribute(Base):
    __tablename__ = 'search_attributes'

    id = Column(Integer, primary_key=True, server_default=text("nextval('search_attributes_id_seq1'::regclass)"))
    search_forum_num = Column(Integer)
    attribute_name = Column(String)
    attribute_value = Column(String)
    timestamp = Column(DateTime)


class SearchCoordinate(Base):
    __tablename__ = 'search_coordinates'

    id = Column(Integer, primary_key=True, server_default=text("nextval('search_activities_id_seq'::regclass)"))
    search_id = Column(Integer)
    activity_type = Column(String)
    latitude = Column(String)
    longitude = Column(String)
    upd_time = Column(DateTime)
    coord_type = Column(String)


class SearchFirstPost(Base):
    __tablename__ = 'search_first_posts'

    id = Column(Integer, primary_key=True, server_default=text("nextval('search_first_posts_id_seq1'::regclass)"))
    search_id = Column(Integer)
    timestamp = Column(DateTime)
    actual = Column(Boolean)
    content_hash = Column(String)
    content = Column(String)
    num_of_checks = Column(Integer)
    coords = Column(String)
    field_trip = Column(String)
    content_compact = Column(String)


t_search_first_posts__history = Table(
    'search_first_posts__history',
    metadata,
    Column('id', Integer, nullable=False),
    Column('search_id', Integer),
    Column('timestamp', DateTime),
    Column('actual', Boolean),
    Column('content_hash', String),
    Column('content', String),
    Column('num_of_checks', Integer),
    Column('coords', String),
    Column('field_trip', String),
    Column('content_compact', String),
)


class SearchHealthCheck(Base):
    __tablename__ = 'search_health_check'

    id = Column(Integer, primary_key=True, server_default=text("nextval('search_health_check_id_seq1'::regclass)"))
    search_forum_num = Column(Integer)
    timestamp = Column(DateTime)
    status = Column(String(50))


class SearchLocation(Base):
    __tablename__ = 'search_locations'

    id = Column(Integer, primary_key=True, server_default=text("nextval('search_locations_id_seq1'::regclass)"))
    search_id = Column(BigInteger)
    address = Column(String(50))
    timestamp = Column(DateTime)


class SearchPlace(Base):
    __tablename__ = 'search_places'

    id = Column(Integer, primary_key=True, server_default=text("nextval('search_places_id_seq1'::regclass)"))
    search_id = Column(Integer)
    address = Column(String)
    timestamp = Column(DateTime)
    debug_title = Column(String)


class Search(Base):
    __tablename__ = 'searches'

    search_forum_num = Column(Integer)
    parsed_time = Column(DateTime)
    status_short = Column(String(255))
    forum_search_title = Column(String(255))
    cut_link = Column(String(255))
    search_start_time = Column(DateTime)
    num_of_replies = Column(Integer)
    family_name = Column(String(255))
    age = Column(Integer)
    id = Column(Integer, primary_key=True, server_default=text("nextval('searches_id_seq1'::regclass)"))
    forum_folder_id = Column(Integer)
    topic_type = Column(String(30))
    display_name = Column(String(100))
    age_min = Column(Integer)
    age_max = Column(Integer)
    status = Column(String(20))
    city_locations = Column(String)
    topic_type_id = Column(Integer)


class StatApiUsageActualSearch(Base):
    __tablename__ = 'stat_api_usage_actual_searches'

    id = Column(
        Integer, primary_key=True, server_default=text("nextval('stat_api_usage_actual_searches_id_seq1'::regclass)")
    )
    timestamp = Column(DateTime)
    request = Column(String)
    response = Column(JSON)


class StatMapUsage(Base):
    __tablename__ = 'stat_map_usage'

    id = Column(Integer, primary_key=True, server_default=text("nextval('stat_map_usage_id_seq1'::regclass)"))
    user_id = Column(BigInteger)
    timestamp = Column(DateTime)
    response = Column(JSON)


t_temp_my_devisions = Table(
    'temp_my_devisions', metadata, Column('forum_folder_num', Integer), Column('user_id', BigInteger)
)


class UserAttribute(Base):
    __tablename__ = 'user_attributes'

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_attributes_id_seq2'::regclass)"))
    forum_user_id = Column(Integer)
    forum_username = Column(String)
    callsign = Column(String)
    region = Column(String)
    auto_num = Column(String)
    phone = Column(String)
    timestamp = Column(DateTime)
    firstname = Column(String)
    lastname = Column(String)
    user_id = Column(BigInteger)


class UserCoordinate(Base):
    __tablename__ = 'user_coordinates'

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_coordinates_id_seq1'::regclass)"))
    latitude = Column(String)
    longitude = Column(String)
    upd_time = Column(DateTime)
    user_id = Column(BigInteger)


class UserForumAttribute(Base):
    __tablename__ = 'user_forum_attributes'

    forum_user_id = Column(Integer)
    forum_username = Column(String)
    forum_age = Column(Integer)
    forum_sex = Column(String)
    forum_region = Column(String)
    forum_auto_num = Column(String)
    forum_callsign = Column(String)
    forum_phone = Column(String)
    forum_reg_date = Column(String)
    status = Column(String)
    timestamp = Column(DateTime)
    id = Column(Integer, primary_key=True, server_default=text("nextval('user_attributes_id_seq'::regclass)"))
    user_id = Column(BigInteger)


class UserOnboarding(Base):
    __tablename__ = 'user_onboarding'

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_onboarding_id_seq1'::regclass)"))
    user_id = Column(BigInteger)
    step_name = Column(String(15))
    timestamp = Column(DateTime)
    step_id = Column(Integer)


class UserPrefAge(Base):
    __tablename__ = 'user_pref_age'
    __table_args__ = (UniqueConstraint('user_id', 'period_min', 'period_max'),)

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_pref_age_id_seq1'::regclass)"))
    user_id = Column(BigInteger)
    period_name = Column(String(30))
    period_set_date = Column(DateTime)
    period_min = Column(Integer)
    period_max = Column(Integer)


class UserPrefRadiu(Base):
    __tablename__ = 'user_pref_radius'

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_pref_radius_id_seq1'::regclass)"))
    user_id = Column(BigInteger, unique=True)
    type = Column(String(10))
    radius = Column(Integer)


class UserPrefRegion(Base):
    __tablename__ = 'user_pref_region'

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_pref_region_id_seq1'::regclass)"))
    user_id = Column(BigInteger)
    region_id = Column(Integer)
    timestamp = Column(DateTime)


t_user_pref_search_filtering = Table(
    'user_pref_search_filtering',
    metadata,
    Column('user_id', BigInteger, nullable=False, unique=True),
    Column('filter_name', ARRAY(String())),
    Column('filter_id', Integer),
)


class UserPrefTopicType(Base):
    __tablename__ = 'user_pref_topic_type'
    __table_args__ = (UniqueConstraint('user_id', 'topic_type_id'),)

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_pref_topic_type_id_seq1'::regclass)"))
    user_id = Column(BigInteger)
    timestamp = Column(DateTime)
    topic_type_id = Column(Integer)
    topic_type_name = Column(String(20))


class UserPrefUrgency(Base):
    __tablename__ = 'user_pref_urgency'

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_pref_urgency_id_seq1'::regclass)"))
    user_id = Column(BigInteger)
    pref_id = Column(Integer)
    pref_name = Column(String(15))
    timestamp = Column(DateTime)


class UserPreference(Base):
    __tablename__ = 'user_preferences'
    __table_args__ = (Index('index_usr_prefs__user_id_and_pref_id', 'user_id', 'pref_id', unique=True),)

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_preferences_id_seq1'::regclass)"))
    preference = Column(String(255))
    user_id = Column(BigInteger)
    pref_id = Column(Integer)


class UserRegionalPreference(Base):
    __tablename__ = 'user_regional_preferences'

    id = Column(
        Integer, primary_key=True, server_default=text("nextval('user_regional_preferences_id_seq1'::regclass)")
    )
    forum_folder_num = Column(Integer)
    user_id = Column(BigInteger)


class UserRole(Base):
    __tablename__ = 'user_roles'

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_roles_id_seq1'::regclass)"))
    role = Column(String)
    user_id = Column(BigInteger)


class UserStat(Base):
    __tablename__ = 'user_stat'

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_stat_id_seq1'::regclass)"))
    num_of_new_search_notifs = Column(Integer)
    user_id = Column(BigInteger, unique=True)


class UserStatusesHistory(Base):
    __tablename__ = 'user_statuses_history'
    __table_args__ = (Index('index_user_statuses_hist', 'user_id', 'date', unique=True),)

    id = Column(Integer, primary_key=True, server_default=text("nextval('user_statuses_history_id_seq1'::regclass)"))
    status = Column(String)
    date = Column(DateTime)
    user_id = Column(BigInteger)


t_user_view = Table(
    'user_view',
    metadata,
    Column('user_id', BigInteger),
    Column('reg_date', DateTime),
    Column('reg_period', Text),
    Column('act_status', Text),
    Column('notif_setting', Text),
    Column('folder_setting', Text),
    Column('receives_summaries', Text),
    Column('onb_step', Integer),
    Column('last_msg', Text),
    Column('last_msg_start', Text),
    Column('last_msg_role', Text),
    Column('last_msg_moscow', Text),
    Column('last_msg_reg', Text),
)


t_user_view_21 = Table(
    'user_view_21',
    metadata,
    Column('user_id', BigInteger),
    Column('folder_setting', Text),
    Column('onb_step', Integer),
    Column('last_msg', Text),
    Column('last_msg_start', Text),
    Column('last_msg_role', Text),
    Column('last_msg_moscow', Text),
    Column('last_msg_reg', Text),
)


t_user_view_21_new = Table(
    'user_view_21_new',
    metadata,
    Column('user_id', BigInteger),
    Column('folder_setting', Text),
    Column('onb_step', Integer),
    Column('last_msg_reg', Text),
)


t_user_view_80 = Table(
    'user_view_80',
    metadata,
    Column('user_id', BigInteger),
    Column('notif_setting', Text),
    Column('receives_summaries', Text),
    Column('onb_step', Integer),
)


t_user_view_80_wo_last_msg = Table(
    'user_view_80_wo_last_msg',
    metadata,
    Column('user_id', BigInteger),
    Column('notif_setting', Text),
    Column('folder_setting', Text),
    Column('onb_step', Integer),
    Column('last_msg', Text),
)


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, server_default=text("nextval('users_id_seq1'::regclass)"))
    username_telegram = Column(String)
    reg_date = Column(DateTime)
    status = Column(String)
    status_change_date = Column(DateTime)
    user_id = Column(BigInteger, unique=True)
    role = Column(String(255))


class NotifMailing(Base):
    __tablename__ = 'notif_mailings'

    mailing_id = Column(
        Integer, primary_key=True, server_default=text("nextval('notif_mailings_mailing_id_seq1'::regclass)")
    )
    topic_id = Column(Integer, nullable=False)
    source_script = Column(String(200))
    mailing_type = Column(ForeignKey('dict_notif_types.type_id'))
    change_log_id = Column(Integer, nullable=False)

    dict_notif_type = relationship('DictNotifType')


class UserPrefSearchWhitelist(Base):
    __tablename__ = 'user_pref_search_whitelist'
    __table_args__ = (Index('idx_user_search_unique', 'user_id', 'search_id', unique=True),)

    id = Column(
        Integer, primary_key=True, server_default=text("nextval('user_pref_search_whitelist_id_seq1'::regclass)")
    )
    user_id = Column(ForeignKey('users.user_id'))
    search_id = Column(Integer)
    timestamp = Column(DateTime)
    search_following_mode = Column(String(30))

    user = relationship('User')


class NotifByUser(Base):
    __tablename__ = 'notif_by_user'

    message_id = Column(
        BigInteger, primary_key=True, server_default=text("nextval('notif_by_user_message_id_seq1'::regclass)")
    )
    mailing_id = Column(ForeignKey('notif_mailings.mailing_id'))
    user_id = Column(BigInteger, nullable=False)
    message_content = Column(String)
    message_text = Column(String)
    message_type = Column(String(50), nullable=False)
    message_params = Column(String)
    message_group_id = Column(Integer)
    change_log_id = Column(Integer)
    created = Column(DateTime)
    completed = Column(DateTime)
    cancelled = Column(DateTime)
    failed = Column(DateTime)
    num_of_fails = Column(Integer)

    mailing = relationship('NotifMailing')


class NotifMailingStatu(Base):
    __tablename__ = 'notif_mailing_status'

    id = Column(Integer, primary_key=True, server_default=text("nextval('notif_mailing_status_id_seq1'::regclass)"))
    mailing_id = Column(ForeignKey('notif_mailings.mailing_id'))
    event = Column(String(100))
    event_timestamp = Column(DateTime)

    mailing = relationship('NotifMailing')
