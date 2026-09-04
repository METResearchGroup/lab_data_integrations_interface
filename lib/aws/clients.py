"""Shared boto3 client construction and DynamoDB error-code lookup."""

from __future__ import annotations

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

CONDITIONAL_CHECK_FAILED = "ConditionalCheckFailedException"


def error_code(error: ClientError) -> str:
    """Return the AWS error code string from a ClientError, or empty if absent."""

    raise NotImplementedError


def build_client(service_name: str, region: str, config: Config | None):
    """Build a boto3 client for one AWS service in one region."""

    raise NotImplementedError


def build_dynamodb_client(region: str, config: Config | None):
    """Build a DynamoDB client."""

    raise NotImplementedError


def build_sqs_client(region: str, config: Config | None):
    """Build an SQS client."""

    raise NotImplementedError


def build_s3_client(region: str, config: Config | None):
    """Build an S3 client."""

    raise NotImplementedError


def build_athena_client(region: str, config: Config | None):
    """Build an Athena client."""

    raise NotImplementedError
