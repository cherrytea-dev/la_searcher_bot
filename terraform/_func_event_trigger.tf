# Deploy functions that should be started by trigger in MessageQueue

variable "event-funcs" {
  type = map(object({
    memory = string
    entrypoint = string
    topic_name = string
  }))
  default = {
    "compose-notifications" = { memory = "256", entrypoint = "foo.main.main", topic_name = "topic_for_notification"}
    "connect-to-forum" = { memory = "256", entrypoint = "foo.main.main", topic_name = "parse_user_profile_from_forum"}
    "identify-updates-of-first-posts" = { memory = "256", entrypoint = "foo.main.main", topic_name = "topic_for_first_post_processing"}
    "identify-updates-of-topics" = { memory = "512", entrypoint = "foo.main.main", topic_name = "topic_to_run_parsing_script"}
    "send-debug-to-admin" = { memory = "256", entrypoint = "foo.main.main", topic_name = "topic_notify_admin"}
    "send-notifications" = { memory = "256", entrypoint = "foo.main.main", topic_name = "topic_to_send_notifications"}
    "archive-notifications" = { memory = "256", entrypoint = "foo.main.main", topic_name = "topic_to_archive_notifs"}
    # next are not active yet
    # "users-activate" = { memory = "256", entrypoint = "foo.main.main", topic_name = "____"}
  }
}

resource "yandex_function" "event-based-func" {
  for_each = var.event-funcs
    
  name        = each.key

  entrypoint = each.value.entrypoint
  memory = each.value.memory

  runtime = var.function_runtime
  environment = var.function_environment
  user_hash = yandex_iam_service_account.sa.id
  content {
    zip_filename = var.function_zip_example
  }
}

resource "yandex_message_queue" "event-queue" {
  for_each = var.event-funcs
    
  name        = each.value.topic_name
}

resource "yandex_function_trigger" "event-trigger" {
  for_each = var.event-funcs

  name        = each.key
  message_queue {
    queue_id           = yandex_message_queue.event-queue[each.key].arn
    service_account_id = yandex_iam_service_account.sa.id
    batch_size         = 1
    batch_cutoff       = 1
  }
  function {
    id = yandex_function.event-based-func[each.key].id
    service_account_id = yandex_iam_service_account.sa.id
  }
}

