from __future__ import annotations

from urllib.parse import quote

from jarvis.apps.browser.browser_context import BrowserContext
from jarvis.apps.browser.interfaces import IBrowserController

# All operations currently open a well-known Gmail URL. A future
# backend (Gmail API / IMAP) can be plugged in under the same service
# surface so the rest of the app doesn't change.
_GMAIL_INBOX = "https://mail.google.com/mail/u/0/#inbox"
_GMAIL_UNREAD = "https://mail.google.com/mail/u/0/#search/is%3Aunread"
_GMAIL_IMPORTANT = "https://mail.google.com/mail/u/0/#important"
_GMAIL_SEARCH = "https://mail.google.com/mail/u/0/#search/"


class EmailService:
    """Email operations by opening pre-filtered Gmail URLs.

    Read/summarize/reply are intentionally NOT implemented here — they
    need a real backend (Gmail API) that can fetch message content.
    The service returns success=False for those so the user and the
    LLM know the limitation.
    """

    def __init__(self, controller: IBrowserController, context: BrowserContext) -> None:
        self._controller = controller
        self._context = context

    def open_inbox(self) -> bool:
        return self._open(_GMAIL_INBOX, "gmail")

    def open_unread(self) -> bool:
        return self._open(_GMAIL_UNREAD, "gmail:unread")

    def open_important(self) -> bool:
        return self._open(_GMAIL_IMPORTANT, "gmail:important")

    def search_from(self, sender: str) -> bool:
        sender = sender.strip()
        if not sender:
            return False
        url = f"{_GMAIL_SEARCH}{quote(f'from:{sender}')}"
        if not self._open(url, f"gmail:from:{sender}"):
            return False
        self._context.remember_email_query(f"from:{sender}")
        return True

    def search_subject(self, subject: str) -> bool:
        subject = subject.strip()
        if not subject:
            return False
        url = f"{_GMAIL_SEARCH}{quote(f'subject:{subject}')}"
        if not self._open(url, f"gmail:subject:{subject}"):
            return False
        self._context.remember_email_query(f"subject:{subject}")
        return True

    def count_unread(self) -> int | None:
        """Not implemented in the URL-only backend — needs Gmail API."""
        return None

    def _open(self, url: str, alias: str) -> bool:
        if not self._controller.open_url(url, new_tab=True):
            return False
        self._context.remember_site(alias=alias, url=url)
        return True
