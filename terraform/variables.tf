variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "GCP region for resources"
}

variable "enable_model_scoring" {
  type        = bool
  default     = false
  description = "Enable optional OpenAI model-driven scoring"
}

variable "container_image_tag" {
  type        = string
  default     = "latest"
  description = "Container image tag to deploy"
}

variable "cloud_run_memory" {
  type        = string
  default     = "1Gi"
  description = "Memory allocation for Cloud Run service"
}

variable "cloud_run_cpu" {
  type        = string
  default     = "2"
  description = "CPU allocation for Cloud Run service"
}

variable "enable_public_access" {
  type        = bool
  default     = true
  description = "Enable public access to Cloud Run service (allUsers)"
}
