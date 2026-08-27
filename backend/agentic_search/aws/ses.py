"""The slice of SES that mailing a finished query needs."""

from __future__ import annotations

import boto3

from bluesky_ingestion_jetstream.aws.constants import AWS_REGION


class SES:
    def __init__(self, sender: str, region: str = AWS_REGION) -> None:
        self.sender = sender
        self.client = boto3.client("sesv2", region_name=region)

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Until SES production access is granted, `to` must be a verified address."""

        self.client.send_email(
            FromEmailAddress=self.sender,
            Destination={"ToAddresses": [to]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject},
                    "Body": {"Text": {"Data": body}},
                }
            },
        )
