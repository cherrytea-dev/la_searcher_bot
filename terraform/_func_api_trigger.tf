# Deploy functions that should be started by Api request

variable "api-funcs" {
  type = map(object({
    memory = string
    entrypoint = string
  }))
  default = {
    "communicate" = { memory = "512", entrypoint = "foo.main.main" }
    "api-get-active-searches" = { memory = "256", entrypoint = "foo.main.main" }
    "title-recognize" = { memory = "1024", entrypoint = "foo.main.main" }
    "user-provide-info" = { memory = "256", entrypoint = "foo.main.main" }
  }
}


resource "yandex_function" "api-based-func" {
  for_each = var.api-funcs
    
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
