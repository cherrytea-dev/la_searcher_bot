test:
	pytest .

lint:
	ruff format src tests --line-length=120 --config "format.quote-style = 'single'"
	ruff check src tests --fix --line-length=120 --config "format.quote-style = 'single'"

lint-check:
	ruff check src tests --line-length=120 --config "format.quote-style = 'single'"
	ruff format src tests --check --line-length=120 --config "format.quote-style = 'single'"


requirements:
	uv export --extra api_get_active_searches  > src/api_get_active_searches/requirements.txt
	uv export --extra archive_notifications  > src/archive_notifications/requirements.txt
	uv export --extra archive_to_bigquery  > src/archive_to_bigquery/requirements.txt
	uv export --extra check_first_posts_for_changes  > src/check_first_posts_for_changes/requirements.txt
	uv export --extra check_topics_by_upd_time  > src/check_topics_by_upd_time/requirements.txt
	uv export --extra communicate  > src/communicate/requirements.txt
	uv export --extra compose_notifications  > src/compose_notifications/requirements.txt
	uv export --extra connect_to_forum  > src/connect_to_forum/requirements.txt
	uv export --extra identify_updates_of_first_posts  > src/identify_updates_of_first_posts/requirements.txt
	uv export --extra identify_updates_of_folders  > src/identify_updates_of_folders/requirements.txt
	uv export --extra identify_updates_of_topics  > src/identify_updates_of_topics/requirements.txt
	uv export --extra manage_users  > src/manage_users/requirements.txt
	uv export --extra send_debug_to_admin  > src/send_debug_to_admin/requirements.txt
	uv export --extra send_news  > src/send_news/requirements.txt
	uv export --extra send_notifications  > src/send_notifications/requirements.txt
	uv export --extra send_notifications_helper  > src/send_notifications_helper/requirements.txt
	uv export --extra send_notifications_helper_2  > src/send_notifications_helper_2/requirements.txt
	uv export --extra title_recognize  > src/title_recognize/requirements.txt
	uv export --extra user_provide_info  > src/user_provide_info/requirements.txt
	uv export --extra users_activate  > src/users_activate/requirements.txt
