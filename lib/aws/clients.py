"""Shared boto3 client construction."""

from __future__ import annotations

import boto3
from botocore.config import Config


def build_client(service_name: str, region: str, config: Config | None):
    """Build a boto3 client for one AWS service in one region.

    Parameters
    ----------
    config
        Botocore retry and timeout settings. When None, boto3 keeps its defaults.
    """

    if config is None:
        return boto3.client(service_name, region_name=region)
    return boto3.client(service_name, region_name=region, config=config)


def build_dynamodb_client(region: str, config: Config | None):
    """Build a DynamoDB client."""

    return build_client("dynamodb", region, config)


def build_sqs_client(region: str, config: Config | None):
    """Build an SQS client."""

    return build_client("sqs", region, config)


def build_s3_client(region: str, config: Config | None):
    """Build an S3 client."""

    return build_client("s3", region, config)


def build_athena_client(region: str, config: Config | None):
    """Build an Athena client."""

    return build_client("athena", region, config)
