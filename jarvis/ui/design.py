"""Design tokens for the Jarvis HUD.

Single source of truth for colors, typography, spacing and the shared
QSS fragment every dialog/window imports. Changing a swatch here
propagates through the whole UI without hunting inline styles.

The palette is deliberately narrow — two families (cyan primary,
amber/magenta accent) plus a five-step neutral scale — so the HUD
reads as a coherent instrument, not a painting.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Color palette ─────────────────────────────────────────────────────
# Named by role, not by hue, so a future theme swap only touches these
# constants.  The `hex` strings here are the canonical source; the
# `Color.rgba_css(alpha)` helper renders the Qt rgba() form when a
# stylesheet needs transparency.


@dataclass(frozen=True, slots=True)
class Color:
    hex: str
    r: int
    g: int
    b: int

    @classmethod
    def from_hex(cls, h: str) -> "Color":
        s = h.lstrip("#")
        return cls(hex=f"#{s}", r=int(s[0:2], 16), g=int(s[2:4], 16), b=int(s[4:6], 16))

    def rgba_css(self, alpha: float) -> str:
        """Qt stylesheet-friendly rgba literal. `alpha` is 0..1."""
        return f"rgba({self.r}, {self.g}, {self.b}, {alpha:.3f})"


# Surface (depths of the dark UI — from deepest background to raised card).
SURFACE_BASE = Color.from_hex("#05080C")
SURFACE_SUNKEN = Color.from_hex("#070B10")
SURFACE_CARD = Color.from_hex("#0C1218")
SURFACE_RAISED = Color.from_hex("#111925")
SURFACE_HOVER = Color.from_hex("#15202D")

# Text scale.
TEXT_PRIMARY = Color.from_hex("#EAFCFF")
TEXT_SECONDARY = Color.from_hex("#C2DDE6")
TEXT_MUTED = Color.from_hex("#7FA2B0")
TEXT_DIM = Color.from_hex("#4A6572")

# Accent palette — strict Jarvis HUD discipline: one primary hue
# (cyan) with two supporting tones (warm amber for attention, teal
# for healthy). No magenta / pink / red. Every state maps to one of
# these three; anything that previously used magenta now uses amber.
ACCENT_PRIMARY = Color.from_hex("#00F0FF")  # cyan — default / listening / AI
ACCENT_SOFT = Color.from_hex("#6EEAFF")  # paler cyan — speaking / secondary highlight
ACCENT_WARM = Color.from_hex("#FFD56B")  # amber — processing / warning / hot values
ACCENT_OK = Color.from_hex("#3DF5C2")  # teal — success / healthy / active provider

# Stroke/border.
BORDER_SUBTLE = Color.from_hex("#1E2B38")
BORDER_ACCENT = ACCENT_PRIMARY


# ── Spacing + radius (4-point grid) ───────────────────────────────────
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 20
SPACE_6 = 24
SPACE_8 = 32
SPACE_10 = 40

RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 22


# ── Typography ────────────────────────────────────────────────────────
FONT_DISPLAY = "Bahnschrift"
FONT_UI = "Bahnschrift"
FONT_MONO = "JetBrains Mono, Consolas"

FONT_SIZE_DISPLAY = 34
FONT_SIZE_TITLE = 18
FONT_SIZE_BODY = 13
FONT_SIZE_SMALL = 11
FONT_SIZE_MICRO = 10


# ── Global stylesheet fragment ────────────────────────────────────────
# Every top-level dialog/window applies this via `setStyleSheet`. Keeps
# base widget styling (QWidget, QPushButton, QLineEdit, etc.) consistent
# so component-specific stylesheets can override selectively instead of
# redefining the whole look.


def global_stylesheet() -> str:
    """Return the master QSS for the app. Computed (not a constant) so
    colour tokens are resolved once at import and future theme hooks
    can swap the palette without restarting."""
    return f"""
QDialog, QMainWindow, QWidget#rootFrame {{
    background: transparent;
    color: {TEXT_PRIMARY.hex};
    font-family: {FONT_UI};
}}

QWidget#rootFrame {{
    background-color: {SURFACE_BASE.rgba_css(0.965)};
    border: 1px solid {BORDER_SUBTLE.hex};
    border-radius: {RADIUS_XL}px;
}}

QLabel {{
    color: {TEXT_PRIMARY.hex};
    font-family: {FONT_UI};
    font-size: {FONT_SIZE_BODY}px;
}}

QLabel[role="display"] {{
    color: {TEXT_PRIMARY.hex};
    font-family: {FONT_DISPLAY};
    font-size: {FONT_SIZE_DISPLAY}px;
    font-weight: 700;
    letter-spacing: 12px;
}}

QLabel[role="title"] {{
    color: {TEXT_PRIMARY.hex};
    font-family: {FONT_UI};
    font-size: {FONT_SIZE_TITLE}px;
    font-weight: 700;
    letter-spacing: 4px;
}}

QLabel[role="subtitle"] {{
    color: {TEXT_MUTED.hex};
    font-family: {FONT_UI};
    font-size: {FONT_SIZE_SMALL}px;
    letter-spacing: 3px;
}}

QLabel[role="muted"] {{
    color: {TEXT_MUTED.hex};
    font-family: {FONT_UI};
    font-size: {FONT_SIZE_SMALL}px;
}}

QLabel[role="header"] {{
    color: {ACCENT_PRIMARY.rgba_css(0.75)};
    font-family: {FONT_UI};
    font-size: {FONT_SIZE_MICRO}px;
    font-weight: 600;
    letter-spacing: 6px;
    padding-bottom: {SPACE_2}px;
    border-bottom: 1px solid {BORDER_SUBTLE.hex};
}}

QPushButton {{
    background-color: {SURFACE_CARD.rgba_css(0.75)};
    border: 1px solid {BORDER_SUBTLE.hex};
    border-radius: {RADIUS_MD}px;
    color: {TEXT_PRIMARY.hex};
    font-family: {FONT_UI};
    font-size: {FONT_SIZE_BODY}px;
    letter-spacing: 2px;
    padding: {SPACE_2}px {SPACE_4}px;
}}

QPushButton:hover {{
    background-color: {SURFACE_HOVER.rgba_css(0.9)};
    border: 1px solid {ACCENT_PRIMARY.rgba_css(0.55)};
    color: {TEXT_PRIMARY.hex};
}}

QPushButton:disabled {{
    color: {TEXT_DIM.hex};
    background-color: {SURFACE_SUNKEN.rgba_css(0.6)};
    border: 1px solid {BORDER_SUBTLE.rgba_css(0.5)};
}}

QPushButton[variant="primary"] {{
    background-color: {ACCENT_PRIMARY.rgba_css(0.18)};
    border: 1px solid {ACCENT_PRIMARY.rgba_css(0.55)};
    color: {TEXT_PRIMARY.hex};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background-color: {ACCENT_PRIMARY.rgba_css(0.32)};
    border: 1px solid {ACCENT_PRIMARY.rgba_css(0.75)};
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    border: 1px solid {BORDER_SUBTLE.hex};
    color: {TEXT_SECONDARY.hex};
}}
QPushButton[variant="ghost"]:hover {{
    background-color: {SURFACE_HOVER.rgba_css(0.6)};
    color: {TEXT_PRIMARY.hex};
    border: 1px solid {ACCENT_PRIMARY.rgba_css(0.4)};
}}

QPushButton[variant="link"] {{
    background-color: {ACCENT_PRIMARY.rgba_css(0.06)};
    border: 1px dashed {ACCENT_PRIMARY.rgba_css(0.4)};
    color: {ACCENT_PRIMARY.rgba_css(0.85)};
    text-align: left;
    padding: {SPACE_3}px {SPACE_4}px;
}}
QPushButton[variant="link"]:hover {{
    background-color: {ACCENT_PRIMARY.rgba_css(0.15)};
    color: {TEXT_PRIMARY.hex};
}}

QPushButton[variant="icon"] {{
    background-color: {SURFACE_CARD.rgba_css(0.45)};
    border: 1px solid {BORDER_SUBTLE.hex};
    border-radius: {RADIUS_LG}px;
    color: {TEXT_SECONDARY.hex};
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_TITLE}px;
    padding: 0;
}}
QPushButton[variant="icon"]:hover {{
    background-color: {ACCENT_PRIMARY.rgba_css(0.15)};
    color: {TEXT_PRIMARY.hex};
    border: 1px solid {ACCENT_PRIMARY.rgba_css(0.45)};
}}

QLineEdit {{
    background-color: {SURFACE_SUNKEN.rgba_css(0.92)};
    border: 1px solid {BORDER_SUBTLE.hex};
    border-radius: {RADIUS_SM}px;
    color: {TEXT_PRIMARY.hex};
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_BODY}px;
    padding: {SPACE_2}px {SPACE_3}px;
    selection-background-color: {ACCENT_PRIMARY.rgba_css(0.3)};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT_PRIMARY.rgba_css(0.65)};
}}

QCheckBox {{
    color: {TEXT_SECONDARY.hex};
    font-family: {FONT_UI};
    font-size: {FONT_SIZE_SMALL}px;
}}

QTextEdit {{
    background-color: {SURFACE_SUNKEN.rgba_css(0.85)};
    border: 1px solid {BORDER_SUBTLE.hex};
    border-radius: {RADIUS_MD}px;
    color: {TEXT_SECONDARY.hex};
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_SMALL}px;
    padding: {SPACE_3}px {SPACE_4}px;
    selection-background-color: {ACCENT_PRIMARY.rgba_css(0.28)};
}}

QTabWidget::pane {{
    background-color: {SURFACE_CARD.rgba_css(0.55)};
    border: 1px solid {BORDER_SUBTLE.hex};
    border-radius: {RADIUS_MD}px;
    top: -1px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background-color: {SURFACE_CARD.rgba_css(0.55)};
    border: 1px solid {BORDER_SUBTLE.hex};
    border-bottom: none;
    border-top-left-radius: {RADIUS_SM}px;
    border-top-right-radius: {RADIUS_SM}px;
    color: {TEXT_MUTED.hex};
    font-family: {FONT_UI};
    font-size: {FONT_SIZE_MICRO}px;
    letter-spacing: 3px;
    margin-right: {SPACE_1}px;
    padding: {SPACE_2}px {SPACE_4}px;
}}
QTabBar::tab:selected {{
    background-color: {ACCENT_PRIMARY.rgba_css(0.14)};
    color: {TEXT_PRIMARY.hex};
    border: 1px solid {ACCENT_PRIMARY.rgba_css(0.5)};
    border-bottom: none;
}}
QTabBar::tab:hover:!selected {{
    background-color: {SURFACE_HOVER.rgba_css(0.6)};
    color: {TEXT_SECONDARY.hex};
}}

/* QScrollArea's viewport is a plain QWidget child that inherits the
   system base palette (light grey on Windows) unless we force it
   transparent. Same for the inner content widget holding the layout.
   These selectors cover both cases so nothing paints white on top of
   the dark dialog surface. */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QAbstractScrollArea {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background-color: {ACCENT_PRIMARY.rgba_css(0.25)};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {ACCENT_PRIMARY.rgba_css(0.45)};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
"""
