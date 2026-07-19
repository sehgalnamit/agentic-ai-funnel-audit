terraform {
  required_version = ">= 1.0"
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

# Artifact Registry for container images
resource "google_artifact_registry_repository" "agentic_audit" {
  location      = var.region
  repository_id = "agentic-ai-funnel-audit"
  description   = "Container images for agentic AI funnel audit service"
  format        = "DOCKER"

  docker_config {
    immutable_tags = false
  }
}

# Secret Manager for API keys and credentials
resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "openai-api-key"
  replication {
    automatic = true
  }
}

resource "google_secret_manager_secret" "telemetry_source" {
  secret_id = "telemetry-source-config"
  replication {
    automatic = true
  }
}

# Cloud Run for the FastAPI service
resource "google_cloud_run_service" "agentic_audit" {
  name     = "agentic-ai-funnel-audit"
  location = var.region

  template {
    spec {
      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.agentic_audit.repository_id}/agentic-ai-funnel-audit:latest"

        env {
          name = "OPENAI_API_KEY"
          value_source {
            secret_key_ref {
              secret = google_secret_manager_secret.openai_api_key.id
              version = "latest"
            }
          }
        }

        env {
          name  = "AGENTIC_USE_MODEL"
          value = var.enable_model_scoring ? "true" : "false"
        }

        env {
          name  = "AGENTIC_JOB_STORE_BACKEND"
          value = "firestore"
        }

        env {
          name  = "AGENTIC_FIRESTORE_JOB_COLLECTION"
          value = "agentic_audit_jobs"
        }

        ports {
          container_port = 8000
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "1Gi"
          }
        }
      }

      service_account_email = google_service_account.agentic_audit.email
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [google_artifact_registry_repository.agentic_audit]
}

# IAM Service Account for Cloud Run
resource "google_service_account" "agentic_audit" {
  account_id   = "agentic-ai-funnel-audit"
  display_name = "Service account for agentic AI funnel audit"
}

# Grant Cloud Run Invoker role
resource "google_cloud_run_service_iam_member" "public_access" {
  service  = google_cloud_run_service.agentic_audit.name
  location = google_cloud_run_service.agentic_audit.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Grant Secret Manager reader to service account
resource "google_secret_manager_secret_iam_member" "openai_key_access" {
  secret_id = google_secret_manager_secret.openai_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agentic_audit.email}"
}

# Cloud Storage bucket for audit logs and artifacts
resource "google_storage_bucket" "audit_logs" {
  name          = "${var.project_id}-audit-logs"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
    condition {
      age = 90
    }
  }
}

# Shared durable state for asynchronous jobs across Cloud Run instances.
resource "google_firestore_database" "audit_jobs" {
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"
}

resource "google_project_iam_member" "firestore_job_access" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agentic_audit.email}"
}

# Pub/Sub Topic for event-driven idea submission
resource "google_pubsub_topic" "idea_intake" {
  name = "agentic-ai-funnel-audit-ideas"

  labels = {
    service = "agentic-audit"
  }
}

# Pub/Sub Subscription for Cloud Run
resource "google_pubsub_subscription" "idea_intake_subscription" {
  name    = "agentic-ai-funnel-audit-ideas-subscription"
  topic   = google_pubsub_topic.idea_intake.name
  project = var.project_id

  push_config {
    push_endpoint = "${google_cloud_run_service.agentic_audit.status[0].url}/events/pubsub"

    oidc_token_audience {
      audience = google_cloud_run_service.agentic_audit.status[0].url
    }
  }

  depends_on = [google_cloud_run_service.agentic_audit]
}

# Grant Pub/Sub publisher role to service account
resource "google_pubsub_topic_iam_member" "publisher" {
  topic  = google_pubsub_topic.idea_intake.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.agentic_audit.email}"
}

output "cloud_run_url" {
  value       = google_cloud_run_service.agentic_audit.status[0].url
  description = "URL of the deployed agentic audit service"
}

output "artifact_registry" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.agentic_audit.repository_id}"
  description = "Artifact Registry path for container images"
}

output "pubsub_topic" {
  value       = google_pubsub_topic.idea_intake.id
  description = "Pub/Sub topic for idea intake"
}

output "storage_bucket" {
  value       = google_storage_bucket.audit_logs.name
  description = "GCS bucket for audit logs"
}

output "firestore_database" {
  value       = google_firestore_database.audit_jobs.name
  description = "Firestore database used for durable async job state"
}
