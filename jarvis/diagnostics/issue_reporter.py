from __future__ import annotations

import urllib.parse
import webbrowser
from abc import ABC, abstractmethod

from jarvis.diagnostics.crash_report import CrashReport, CrashReporter


class IGitHubIssueReporter(ABC):
    @abstractmethod
    def report(self, report: CrashReport) -> str:
        """Send the report somewhere the maintainer can see it. Return a URL."""


class GitHubUrlIssueReporter(IGitHubIssueReporter):
    """Safest default: open the GitHub new-issue page with a prefilled title
    and body. No tokens, no automatic submission — the user reviews and posts."""

    _MAX_BODY_CHARS = 6000

    def __init__(
        self,
        repo: str,
        crash_reporter: CrashReporter,
        labels: tuple[str, ...] = ("bug", "crash-report"),
    ) -> None:
        if "/" not in repo:
            raise ValueError(f"repo must be 'owner/name', got: {repo!r}")
        self._repo = repo
        self._crash_reporter = crash_reporter
        self._labels = labels

    def build_url(self, report: CrashReport) -> str:
        title = f"[crash] {report.error_type}: {report.error_message[:120]}"
        body = self._crash_reporter.render_markdown(report)
        if len(body) > self._MAX_BODY_CHARS:
            body = (
                body[: self._MAX_BODY_CHARS]
                + "\n\n_...truncated. Full crash file saved locally._"
            )
        params = {
            "title": title,
            "body": body,
            "labels": ",".join(self._labels),
        }
        return f"https://github.com/{self._repo}/issues/new?{urllib.parse.urlencode(params)}"

    def report(self, report: CrashReport) -> str:
        url = self.build_url(report)
        webbrowser.open(url)
        return url


class GitHubApiIssueReporter(IGitHubIssueReporter):
    """Placeholder for future automatic issue creation via the GitHub REST API.

    Not implemented yet — a token-based flow needs an auth story you trust."""

    def __init__(self, repo: str, token: str) -> None:
        self._repo = repo
        self._token = token

    def report(self, report: CrashReport) -> str:  # pragma: no cover
        raise NotImplementedError(
            "GitHubApiIssueReporter is not implemented. "
            "Use GitHubUrlIssueReporter for now."
        )
