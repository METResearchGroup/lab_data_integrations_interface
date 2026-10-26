# Destroy only. Do not apply. Apply would create the distribution again.
# The steps are in docs/runbooks/HOW_TO_DEPLOY_TO_CLOUDFLARE.md
# under "Destroy the CloudFront distribution".

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  backend "s3" {
    bucket       = "lab-data-integrations-interface-tfstate"
    key          = "backend_edge/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}

# CloudFront-scoped WAF must live in us-east-1.
provider "aws" {
  region = "us-east-1"
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "origin_domain" {
  description = "The backend's Railway domain, e.g. abc123.up.railway.app (no scheme)."
  type        = string
}

variable "query_rate_limit" {
  description = "Requests to /query per IP per minute before WAF blocks. Campus users can share an IP."
  type        = number
  default     = 100
}

# ---------------------------------------------------------------------------
# Origin secret: CloudFront adds it, backend/origin.py checks it.
# ---------------------------------------------------------------------------

resource "random_password" "origin_secret" {
  length  = 64
  special = false
}

# ---------------------------------------------------------------------------
# WAF
# ---------------------------------------------------------------------------

resource "aws_wafv2_web_acl" "backend" {
  name  = "backend-edge"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "anti-ddos"
    priority = 0

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAntiDDoSRuleSet"

        managed_rule_group_configs {
          aws_managed_rules_anti_ddos_rule_set {
            sensitivity_to_block = "LOW"

            # Challenges are browser interstitials; an API's fetch() can't solve them.
            client_side_action_config {
              challenge {
                usage_of_action = "DISABLED"
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "anti-ddos"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "query-rate-limit"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.query_rate_limit
        evaluation_window_sec = 60
        aggregate_key_type    = "IP"

        scope_down_statement {
          byte_match_statement {
            search_string         = "/query"
            positional_constraint = "EXACTLY"

            field_to_match {
              uri_path {}
            }

            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "query-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "backend-edge"
    sampled_requests_enabled   = true
  }
}

# ---------------------------------------------------------------------------
# CloudFront
# ---------------------------------------------------------------------------

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

# Railway routes by Host, so the origin must see its own domain, not CloudFront's.
data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "backend" {
  enabled     = true
  comment     = "backend API"
  price_class = "PriceClass_100"
  web_acl_id  = aws_wafv2_web_acl.backend.arn

  origin {
    origin_id   = "railway"
    domain_name = var.origin_domain

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = "X-Origin-Secret"
      value = random_password.origin_secret.result
    }
  }

  default_cache_behavior {
    target_origin_id         = "railway"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "api_url" {
  description = "Set as NEXT_PUBLIC_API_URL in the UI."
  value       = "https://${aws_cloudfront_distribution.backend.domain_name}"
}

output "origin_secret" {
  description = "Set as ORIGIN_SECRET on the Railway backend."
  value       = random_password.origin_secret.result
  sensitive   = true
}
