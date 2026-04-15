from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.diagnostics.crash_report import CrashReport
from jarvis.diagnostics.issue_reporter import IGitHubIssueReporter


class CrashDialog(QDialog):
    def __init__(
        self,
        report: CrashReport,
        issue_reporter: IGitHubIssueReporter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._report = report
        self._issue_reporter = issue_reporter
        self.setWindowTitle("Jarvis — erro inesperado")
        self.setMinimumSize(640, 420)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        headline = QLabel(
            f"Ocorreu um erro inesperado: <b>{self._report.error_type}</b><br/>"
            f"{self._report.error_message}"
        )
        headline.setWordWrap(True)
        layout.addWidget(headline)

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(self._preview_text())
        layout.addWidget(details, 1)

        buttons = QDialogButtonBox()
        report_button = QPushButton("Reportar problema")
        report_button.setDefault(True)
        report_button.clicked.connect(self._on_report_clicked)
        buttons.addButton(report_button, QDialogButtonBox.ButtonRole.AcceptRole)
        close_button = buttons.addButton("Fechar", QDialogButtonBox.ButtonRole.RejectRole)
        close_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _preview_text(self) -> str:
        lines = [
            f"ID: {self._report.id}",
            f"Versão: {self._report.app_version}",
            f"SO: {self._report.operating_system}",
            f"Python: {self._report.python_version}",
            f"Provider: {self._report.provider}",
            f"Ação: {self._report.current_action or '(nenhuma)'}",
            "",
            "Stack trace:",
            self._report.stack_trace,
        ]
        return "\n".join(lines)

    def _on_report_clicked(self) -> None:
        try:
            self._issue_reporter.report(self._report)
        finally:
            self.accept()
