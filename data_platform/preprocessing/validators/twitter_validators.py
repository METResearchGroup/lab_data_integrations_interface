from __future__ import annotations

import re

from data_platform.preprocessing.validators.validators import check_if_post_has_no_urls

_TCO_URL_PATTERN = re.compile(r"https?://t\.co/\S+")


def strip_tco_links(text: str) -> str:
    return _TCO_URL_PATTERN.sub("", text)


def check_if_valid_twitter_post_length(text: str) -> bool:
    return 50 <= len(text) <= 280


def check_if_twitter_text_has_no_external_urls(text: str) -> bool:
    return check_if_post_has_no_urls(strip_tco_links(text))
