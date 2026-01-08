# Text Extraction Service - Terraform Variables

# ============================================================================
# Required Variables
# ============================================================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod"
  }
}

# ============================================================================
# Region Configuration (EU Data Residency)
# ============================================================================

variable "region" {
  description = "GCP region (EU only for GDPR compliance)"
  type        = string
  default     = "europe-west3"

  validation {
    condition     = can(regex("^europe-", var.region))
    error_message = "Region must be in Europe for GDPR compliance"
  }
}

# ============================================================================
# Container Configuration
# ============================================================================

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "cpu_limit" {
  description = "CPU limit for container"
  type        = string
  default     = "2"
}

variable "memory_limit" {
  description = "Memory limit for container"
  type        = string
  default     = "2Gi"
}

variable "min_instances" {
  description = "Minimum number of instances (0 for scale-to-zero)"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 10
}

# ============================================================================
# Application Configuration
# ============================================================================

variable "langdock_ocr_model" {
  description = "Langdock OCR model to use"
  type        = string
  default     = "claude-sonnet-4-5@20250929"
}

variable "tesseract_lang" {
  description = "Tesseract OCR languages"
  type        = string
  default     = "deu+eng"
}

variable "max_file_size_mb" {
  description = "Maximum file size in MB"
  type        = number
  default     = 50
}

variable "default_quality" {
  description = "Default extraction quality"
  type        = string
  default     = "balanced"

  validation {
    condition     = contains(["fast", "balanced", "accurate"], var.default_quality)
    error_message = "Quality must be one of: fast, balanced, accurate"
  }
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "Log level must be one of: DEBUG, INFO, WARNING, ERROR"
  }
}

# ============================================================================
# Access Configuration
# ============================================================================

variable "allow_public_access" {
  description = "Allow unauthenticated public access to the API"
  type        = bool
  default     = false
}
