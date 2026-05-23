output "app_runner_url" {
  value = "https://${aws_apprunner_service.backend.service_url}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}
