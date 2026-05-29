import re

def check_if_not_phone(text: str) -> bool:
    phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|\(\d{3}\)\s?\d{3}[-.]?\d{4}|\b\d{10}\b'
    return not re.search(phone_pattern, text)
