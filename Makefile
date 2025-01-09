venv:
	uv sync --all-groups --all-extras

test:
	pytest .

lint:
	ruff format src tests --line-length=120 --config "format.quote-style = 'single'"
	ruff check src tests --fix --line-length=120 --config "format.quote-style = 'single'"

lint-check:
	ruff check src tests --line-length=120 --config "format.quote-style = 'single'"
	ruff format src tests --check --line-length=120 --config "format.quote-style = 'single'"

requirements:
	uv export --extra api_get_active_searches --no-hashes > src/api_get_active_searches/requirements.txt
	uv export --extra archive_notifications --no-hashes > src/archive_notifications/requirements.txt
	uv export --extra archive_to_bigquery --no-hashes > src/archive_to_bigquery/requirements.txt
	uv export --extra check_first_posts_for_changes --no-hashes > src/check_first_posts_for_changes/requirements.txt
	uv export --extra check_topics_by_upd_time --no-hashes > src/check_topics_by_upd_time/requirements.txt
	uv export --extra communicate --no-hashes > src/communicate/requirements.txt
	uv export --extra compose_notifications --no-hashes > src/compose_notifications/requirements.txt
	uv export --extra connect_to_forum --no-hashes > src/connect_to_forum/requirements.txt
	uv export --extra identify_updates_of_first_posts --no-hashes > src/identify_updates_of_first_posts/requirements.txt
	uv export --extra identify_updates_of_folders --no-hashes > src/identify_updates_of_folders/requirements.txt
	uv export --extra identify_updates_of_topics --no-hashes > src/identify_updates_of_topics/requirements.txt
	uv export --extra manage_users --no-hashes > src/manage_users/requirements.txt
	uv export --extra send_debug_to_admin --no-hashes > src/send_debug_to_admin/requirements.txt
	uv export --extra send_notifications --no-hashes > src/send_notifications/requirements.txt
	uv export --extra send_notifications_helper --no-hashes > src/send_notifications_helper/requirements.txt
	uv export --extra send_notifications_helper_2 --no-hashes > src/send_notifications_helper_2/requirements.txt
	uv export --extra title_recognize --no-hashes > src/title_recognize/requirements.txt
	uv export --extra user_provide_info --no-hashes > src/user_provide_info/requirements.txt
	uv export --extra users_activate --no-hashes > src/users_activate/requirements.txt
