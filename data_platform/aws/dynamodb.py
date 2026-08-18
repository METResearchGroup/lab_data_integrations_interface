from __future__ import annotations

from typing import Any

import boto3

from data_platform.aws.constants import DEFAULT_REGION


class DynamoDB:
    def __init__(self, region: str = DEFAULT_REGION) -> None:
        self.resource = boto3.resource("dynamodb", region_name=region)

    def put_item(self, table: str, item: dict[str, Any]) -> None:
        self.resource.Table(table).put_item(Item=item)

    def get_item(self, table: str, key: dict[str, Any]) -> dict[str, Any] | None:
        response = self.resource.Table(table).get_item(Key=key)
        return response.get("Item")

    def update_item(
        self,
        table: str,
        key: dict[str, Any],
        updates: dict[str, Any],
    ) -> None:
        """Set one or more attributes on an existing item without overwriting the rest.

        Each key in `updates` is an attribute path, e.g. "stages.ingestion" for a nested
        map field. Every path segment gets its own expression-attribute-name placeholder
        so reserved words (like "status") are always safe to use."""
        set_clauses: list[str] = []
        attr_names: dict[str, str] = {}
        attr_values: dict[str, Any] = {}
        for i, (path, value) in enumerate(updates.items()):
            segments = path.split(".")
            placeholders = [f"#n{i}_{j}" for j in range(len(segments))]
            for placeholder, segment in zip(placeholders, segments, strict=True):
                attr_names[placeholder] = segment
            value_placeholder = f":v{i}"
            attr_values[value_placeholder] = value
            set_clauses.append(f"{'.'.join(placeholders)} = {value_placeholder}")

        self.resource.Table(table).update_item(
            Key=key,
            UpdateExpression="SET " + ", ".join(set_clauses),
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
        )
