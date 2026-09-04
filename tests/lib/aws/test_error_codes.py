from __future__ import annotations

from botocore.exceptions import ClientError

from lib.aws.error_codes import error_code


def _client_error(response: dict) -> ClientError:
    return ClientError(response, "UpdateItem")


class TestErrorCode:
    """Tests for error_code."""

    def test_returns_the_error_code_string(self):
        error = _client_error(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": "failed"}}
        )

        result = error_code(error)
        expected = "ConditionalCheckFailedException"

        assert result == expected

    def test_returns_empty_string_when_error_mapping_is_missing(self):
        error = _client_error({})

        result = error_code(error)
        expected = ""

        assert result == expected
