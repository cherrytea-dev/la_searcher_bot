terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = ">= 0.84.0"
    }
  }
}

provider "yandex" {
  zone = "ru-central1-a"
  # other values in override.tf
}

variable "function_environment" {
  type = map(string)
  default = {}
}

variable "function_runtime" {
  type = string
  default = "python312"
}

variable "function_zip_example" {
  type = string
  default = "testfunc.zip"
}

variable "sa_id" {
  type = string
  default = "place_to_override"
}

import {
  to = yandex_iam_service_account.sa
  id = var.sa_id
}

resource "yandex_iam_service_account" "sa" {
  name        = "la-searcher-bot"
}

