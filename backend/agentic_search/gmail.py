"""The slice of Gmail that mailing a finished query needs."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

SMTP_HOST = "smtp.gmail.com"
SMTP_SSL_PORT = 465


class Gmail:
    def __init__(self, sender: str, password: str) -> None:
        self.sender = sender
        self.password = password

    def send(self, *, to: str, subject: str, body: str, attachment: Path | None = None) -> None:
        """Gmail rewrites From to the authenticated account, so `sender` must be it."""

        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if attachment is not None:
            message.add_attachment(
                attachment.read_bytes(),
                maintype="text",
                subtype="csv",
                filename=attachment.name,
            )

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_SSL_PORT) as smtp:
            smtp.login(self.sender, self.password)
            smtp.send_message(message)
