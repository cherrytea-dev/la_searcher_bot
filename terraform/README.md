# Terraform: first-time scaffold

This folder is a starting point for provisioning the Yandex Cloud side from scratch: the
provider setup, a service account, the Object Storage bucket, and example function/trigger
definitions (`_func_cron_trigger.tf`, `_func_event_trigger.tf`, `_func_api_trigger.tf`).

It is **not** a description of the current deployment. The live cloud deployment is done by
GitHub Actions from [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml), and the
single-container runtime is described in [`doc/single-container.md`](../doc/single-container.md).
The example entries use placeholder names (`foo.main.main`, `testfunc.zip`, `override.tf`) and
do not cover every function in the deploy matrix.
