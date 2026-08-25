import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from bluesky_backfill_app.aws.constants import (
    AWS_REGION,
    DYNAMODB_CONNECT_TIMEOUT_SECONDS,
    DYNAMODB_MAX_ATTEMPTS,
    DYNAMODB_READ_TIMEOUT_SECONDS,
)

CONDITIONAL_CHECK_FAILED = "ConditionalCheckFailedException"


def error_code(error: ClientError) -> str:
    return error.response.get("Error", {}).get("Code", "")


def build_dynamodb_client():
    return boto3.client(
        "dynamodb",
        region_name=AWS_REGION,
        config=Config(
            retries={"max_attempts": DYNAMODB_MAX_ATTEMPTS, "mode": "standard"},
            connect_timeout=DYNAMODB_CONNECT_TIMEOUT_SECONDS,
            read_timeout=DYNAMODB_READ_TIMEOUT_SECONDS,
        ),
    )
