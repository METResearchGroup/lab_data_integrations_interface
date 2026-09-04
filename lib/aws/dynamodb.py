"""Thin DynamoDB store base that owns a client and a table name."""

from __future__ import annotations

from botocore.config import Config

from lib.aws.clients import build_dynamodb_client
from lib.aws.constants import AWS_REGION


class DynamoDBStore:
    """Holds a DynamoDB client and table name for a subclass to use."""

    def __init__(
        self,
        table: str,
        client=None,
        region: str = AWS_REGION,
        config: Config | None = None,
    ) -> None:
        """
        Parameters
        ----------
        config
            Retry and timeout settings for the default client. Ignored when
            ``client`` is passed in.
        """

        self.client = client if client is not None else build_dynamodb_client(region, config)
        self.table = table
