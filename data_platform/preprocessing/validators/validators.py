import re

from langdetect import LangDetectException, detect  # pyright: ignore[reportMissingImports]


def check_if_not_phone(text: str) -> bool:
    phone_pattern = r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|\(\d{3}\)\s?\d{3}[-.]?\d{4}|\b\d{10}\b"
    return not re.search(phone_pattern, text)


def check_if_valid_post_length(text: str) -> bool:
    """For Bluesky/Twitter posts, check if the length is valid.

    (Yes, arbitrary cutoff, but determined by consensus)
    """
    return len(text) >= 100 and len(text) <= 300


def check_if_post_has_no_urls(text: str) -> bool:
    """Checks if a post has no URLs.

    Posts with URLs more often are not "self-encompassing", meaning that the
    meaning of the post often can't be determined from the post alone."""
    url_pattern = (
        r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
        r"|www\.(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),])+"
        r"|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    )
    return not re.search(url_pattern, text)


def check_if_text_english(text: str) -> bool:
    """Return True if langdetect identifies the text as English."""
    if not text.strip():
        return False

    try:
        return detect(text) == "en"
    except LangDetectException:
        return False
