# Deploy functions that should be started by timer

variable "cron-funcs" {
  type = map(object({
    memory = string
    entrypoint = string
  }))
  default = {
    "check-topics-by-upd-time" = { memory = "256", entrypoint = "foo.main.main" }
    "check-first-posts-for-changes" = { memory = "256", entrypoint = "foo.main.main" }
  }
}


resource "yandex_function" "cron-based-func" {
  for_each = var.cron-funcs
    
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

resource "yandex_function_trigger" "cron-trigger" {
  for_each = var.cron-funcs

  name        = each.key
  timer {
    cron_expression = "* * ? * * *"  # every minute
  }
  function {
    id = yandex_function.cron-based-func[each.key].id
    service_account_id = yandex_iam_service_account.sa.id
  }
}

resource "yandex_function_trigger" "cron-trigger-archive-notifications" {
  # add one more trigger for notifications archive
  name        = "archive-notifications-by-cron"
  timer {
    cron_expression = "0 * ? * * *"  # every hour
  }
  function {
    id = yandex_function.event-based-func["archive-notifications"].id
    service_account_id = yandex_iam_service_account.sa.id
  }
}
