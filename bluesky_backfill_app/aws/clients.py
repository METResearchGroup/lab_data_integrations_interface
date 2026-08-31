import boto3
from botocore.exceptions import ClientError

from bluesky_backfill_app.aws.constants import AWS_REGION

CONDITIONAL_CHECK_FAILED = "ConditionalCheckFailedException"


def error_code(error: ClientError) -> str:
    return error.response.get("Error", {}).get("Code", "")


def build_dynamodb_client():
    return boto3.client("dynamodb", region_name=AWS_REGION)


def build_sqs_client():
    return boto3.client("sqs", region_name=AWS_REGION)
