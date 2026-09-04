from __future__ import annotations

import pytest
from botocore.config import Config

from lib.aws import clients as clients_mod
from lib.aws.clients import (
    build_athena_client,
    build_client,
    build_dynamodb_client,
    build_s3_client,
    build_sqs_client,
)


class TestBuildClient:
    """Tests for build_client."""

    def test_omits_config_when_config_is_none(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[tuple[tuple, dict]] = []

        def fake_client(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        monkeypatch.setattr(clients_mod.boto3, "client", fake_client)

        build_client("dynamodb", "us-east-2", None)

        args, kwargs = calls[0]
        assert args == ("dynamodb",)
        assert kwargs["region_name"] == "us-east-2"
        assert "config" not in kwargs

    def test_passes_config_when_provided(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[tuple[tuple, dict]] = []
        config = Config(retries={"max_attempts": 3, "mode": "standard"})

        def fake_client(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        monkeypatch.setattr(clients_mod.boto3, "client", fake_client)

        build_client("s3", "us-east-2", config)

        _args, kwargs = calls[0]
        assert kwargs["config"] is config


class TestBuildServiceClients:
    """Tests for the per-service client builders."""

    @pytest.mark.parametrize(
        "builder,service_name",
        [
            (build_dynamodb_client, "dynamodb"),
            (build_sqs_client, "sqs"),
            (build_s3_client, "s3"),
            (build_athena_client, "athena"),
        ],
    )
    def test_calls_boto3_with_the_service_name(
        self, monkeypatch: pytest.MonkeyPatch, builder, service_name: str
    ):
        calls: list[tuple[tuple, dict]] = []

        def fake_client(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        monkeypatch.setattr(clients_mod.boto3, "client", fake_client)

        builder("us-east-2", None)

        args, kwargs = calls[0]
        assert args == (service_name,)
        assert kwargs["region_name"] == "us-east-2"
        assert "config" not in kwargs
