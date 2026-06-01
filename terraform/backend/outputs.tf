output "backend_url" {
  value = "http://${aws_lb.backend.dns_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}
