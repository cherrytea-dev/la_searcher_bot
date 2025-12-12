terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = ">= 0.84.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "> 5.1"
    }
  }
}

provider "yandex" {
  zone = "ru-central1-a"
  # other values in override.tf
}

provider "aws" {
  region                      = "us-east-1"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  access_key                  = "place_to_override"
  secret_key                  = "place_to_override"
}
variable "function_environment" {
  type = map(string)
  default = {

  }
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

resource "yandex_storage_bucket" "backup_bucket" {
  bucket = "la-backup-notifications"
  default_storage_class = "COLD"
}