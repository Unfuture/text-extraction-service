# Text Extraction Service - Terraform Backend Configuration
#
# Note: The GCS bucket must be created manually before first use:
#   gsutil mb -l europe-west3 gs://text-extraction-terraform-state
#   gsutil versioning set on gs://text-extraction-terraform-state

terraform {
  backend "gcs" {
    bucket = "text-extraction-terraform-state"
    prefix = "terraform/state"
  }
}

# Alternative: Local backend for initial development
# terraform {
#   backend "local" {
#     path = "terraform.tfstate"
#   }
# }
