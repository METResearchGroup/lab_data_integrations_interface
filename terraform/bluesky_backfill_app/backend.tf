# Remote state for this stack. Same bucket as terraform/bluesky_ingestion_jetstream.
terraform {
  backend "s3" {
    bucket       = "lab-data-integrations-interface-tfstate"
    key          = "bluesky_backfill_app/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}
