# Text Extraction Service - Terraform Configuration
# Cloud Run deployment on GCP (europe-west3)

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ============================================================================
# Locals
# ============================================================================

locals {
  service_name = "text-extraction-${var.environment}"
  labels = {
    environment = var.environment
    service     = "text-extraction"
    managed_by  = "terraform"
  }
}

# ============================================================================
# Artifact Registry - Docker Image Repository
# ============================================================================

resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "text-extraction"
  description   = "Docker images for text-extraction service"
  format        = "DOCKER"

  labels = local.labels
}

# ============================================================================
# Service Account for Cloud Run
# ============================================================================

resource "google_service_account" "cloud_run" {
  account_id   = "text-extraction-${var.environment}"
  display_name = "Text Extraction Service (${var.environment})"
  description  = "Service account for text-extraction Cloud Run service"
}

# Grant access to Secret Manager (for LANGDOCK_API_KEY)
resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# ============================================================================
# Secret Manager - API Keys
# ============================================================================

resource "google_secret_manager_secret" "langdock_api_key" {
  secret_id = "langdock-api-key-${var.environment}"

  labels = local.labels

  replication {
    auto {}
  }
}

# Note: Secret version must be created manually or via CI/CD
# gcloud secrets versions add langdock-api-key-dev --data-file=-

# ============================================================================
# Cloud Run Service
# ============================================================================

resource "google_cloud_run_v2_service" "text_extraction" {
  name     = local.service_name
  location = var.region

  labels = local.labels

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/text-extraction/api:${var.image_tag}"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
      }

      # Environment variables
      env {
        name  = "LANGDOCK_OCR_MODEL"
        value = var.langdock_ocr_model
      }

      env {
        name  = "TESSERACT_LANG"
        value = var.tesseract_lang
      }

      env {
        name  = "MAX_FILE_SIZE_MB"
        value = tostring(var.max_file_size_mb)
      }

      env {
        name  = "DEFAULT_QUALITY"
        value = var.default_quality
      }

      env {
        name  = "LOG_LEVEL"
        value = var.log_level
      }

      # Secret from Secret Manager
      env {
        name = "LANGDOCK_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.langdock_api_key.secret_id
            version = "latest"
          }
        }
      }

      # Health check
      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        timeout_seconds   = 5
        period_seconds    = 30
        failure_threshold = 3
      }
    }

    # Request timeout (30s for scanned PDFs)
    timeout = "300s"
  }

  # Traffic configuration
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# ============================================================================
# IAM - Public or Private Access
# ============================================================================

# Allow unauthenticated access (public API)
# Remove this for private API
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  count = var.allow_public_access ? 1 : 0

  project  = google_cloud_run_v2_service.text_extraction.project
  location = google_cloud_run_v2_service.text_extraction.location
  name     = google_cloud_run_v2_service.text_extraction.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
