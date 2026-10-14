"""The slice of Gmail that mailing a finished query needs."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_SSL_PORT = 465


class Gmail:
    def __init__(self, sender: str, password: str) -> None:
        self.sender = sender
        self.password = password

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Gmail rewrites From to the authenticated account, so `sender` must be it."""

        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_SSL_PORT) as smtp:
            smtp.login(self.sender, self.password)
            smtp.send_message(message)
