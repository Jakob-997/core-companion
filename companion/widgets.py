"""Small shared Qt widgets used by both wallet modes."""

from PySide6.QtCore import QByteArray, Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


_ICONS = {
    "scan": '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8m8 0h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16m-8 0H5.5A1.5 1.5 0 0 1 4 18.5V16"/><path d="M7 7h4v4H7zM13 7h4v4h-4zM7 13h4v4H7z"/><path d="M14 14h3v3h-3zM18 13v2m-2 3h2"/>',
    "wallet": '<path d="M4.5 7.5V6A2 2 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5V8"/><path d="M4.5 7.5H18a2 2 0 0 1 2 2v8a2.5 2.5 0 0 1-2.5 2.5h-11a2 2 0 0 1-2-2z"/><path d="M15 11h5v5h-5a2.5 2.5 0 0 1 0-5Z"/>',
    "settings": '<circle cx="12" cy="12" r="3.2"/><path d="m19.4 15 .1.1a1.8 1.8 0 1 1-2.5 2.5l-.1-.1a1.8 1.8 0 0 0-3 .9v.2a1.8 1.8 0 1 1-3.6 0v-.2a1.8 1.8 0 0 0-3-.9l-.1.1a1.8 1.8 0 1 1-2.5-2.5l.1-.1a1.8 1.8 0 0 0-.9-3h-.2a1.8 1.8 0 1 1 0-3.6h.2a1.8 1.8 0 0 0 .9-3l-.1-.1a1.8 1.8 0 1 1 2.5-2.5l.1.1a1.8 1.8 0 0 0 3-.9v-.2a1.8 1.8 0 1 1 3.6 0v.2a1.8 1.8 0 0 0 3 .9l.1-.1a1.8 1.8 0 1 1 2.5 2.5l-.1.1a1.8 1.8 0 0 0 .9 3h.2a1.8 1.8 0 1 1 0 3.6h-.2a1.8 1.8 0 0 0-.9 3Z"/>',
    "receive": '<path d="M12 3v11m-4-4 4 4 4-4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
    "activity": '<path d="M4 14h3l2-7 4 11 2-7h5"/><path d="M4 4h16v16H4z"/>',
    "policy": '<path d="M5 4h14v16H5z"/><path d="M8 8h2v2H8zm0 5h2v2H8zm5-4h3m-3 5h3"/>',
    "export": '<path d="M4 13v6h16v-6M12 15V3m-4 4 4-4 4 4"/>',
    "offline": '<path d="M4 7.5a12 12 0 0 1 16 0M7 10.5a7.5 7.5 0 0 1 10 0M10 13.5a3.2 3.2 0 0 1 4 0"/><path d="m3 3 18 18"/><path d="M12 18.5h.01"/>',
    "cold": '<path d="M12 2.8 19 5.7v5.1c0 4.7-3.1 8-7 10.4-3.9-2.4-7-5.7-7-10.4V5.7l7-2.9Z"/><rect x="8.3" y="10.5" width="7.4" height="5.7" rx="1.2"/><path d="M10 10.5V9a2 2 0 0 1 4 0v1.5"/>',
    "node": '<rect x="3.5" y="4" width="7" height="6" rx="1.4"/><rect x="13.5" y="14" width="7" height="6" rx="1.4"/><rect x="13.5" y="4" width="7" height="6" rx="1.4"/><rect x="3.5" y="14" width="7" height="6" rx="1.4"/><path d="M10.5 7h3m-10 6v1m17-1v1m-10 3h3"/>',
    "new": '<path d="M5 6.5A2.5 2.5 0 0 1 7.5 4H19v15H6.5A2.5 2.5 0 0 1 4 16.5v-8A2 2 0 0 1 6 6.5H19"/><path d="M11.5 9v6m-3-3h6"/>',
    "import": '<path d="M4 14v5h16v-5M12 3v11m-4-4 4 4 4-4M7 3.5h10"/>',
    "key": '<circle cx="8.5" cy="15.5" r="4.5"/><path d="m11.7 12.3 7.8-7.8 2 2-2.4 2.4 1.6 1.6-2.2 2.2-1.6-1.6-2.1 2.1"/>',
    "multisig": '<circle cx="6" cy="7" r="2.4"/><circle cx="18" cy="7" r="2.4"/><circle cx="12" cy="17" r="2.4"/><path d="m8 8.5 2.7 6.2m5.3-6.2-2.7 6.2M8.5 7h7"/>',
}
_ICON_ALIASES = {
    "▦": "scan", "▣": "wallet", "⚙": "settings", "⌘": "policy",
    "↓": "receive", "⇧": "activity", "❄": "cold", "◉": "node",
    "＋": "new", "↻": "import",
}


class LineIcon(QLabel):
    def __init__(self, glyph, object_name, stroke_width=2.05, inset=7):
        super().__init__()
        self.setObjectName(object_name)
        self._paths = _ICONS.get(_ICON_ALIASES.get(glyph, glyph))
        self._stroke_width = stroke_width
        self._inset = inset
        if not self._paths:
            self.setText(glyph)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        if not self._paths:
            return super().paintEvent(event)
        super().paintEvent(event)
        color = self.palette().color(QPalette.ColorRole.WindowText).name()
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="{self._stroke_width}" '
            f'stroke-linecap="round" stroke-linejoin="round">{self._paths}</svg>'
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        painter = QPainter(self)
        bounds = QRectF(self.rect()).adjusted(
            self._inset, self._inset, -self._inset, -self._inset
        )
        renderer.render(painter, bounds)
        painter.end()


class ActionRow(QFrame):
    clicked = Signal()

    def __init__(self, symbol, title, description, *, primary=False, tooltip="", icon_key=None):
        super().__init__()
        self.setObjectName("ActionPrimary" if primary else "ActionRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(tooltip or description)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(13)
        icon = LineIcon(icon_key or symbol, "BlueIcon")
        icon.setFixedSize(36, 36)
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(icon)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("ActionTitle")
        heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy.addWidget(heading)
        if description:
            detail = QLabel(description)
            detail.setObjectName("Muted")
            detail.setWordWrap(True)
            detail.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            copy.addWidget(detail)
        row.addLayout(copy, 1)
        arrow = QLabel("›")
        arrow.setObjectName("Muted")
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(arrow)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ChoiceRow(QPushButton):
    """Compact selectable row matching the wallet mode and setup screens."""

    def __init__(self, symbol, title, description="", *, accent="green", tooltip=""):
        super().__init__()
        self.setObjectName("ChoiceRow")
        self.setProperty("accent", accent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
        if description:
            self.setAccessibleDescription(description)
        self.setToolTip(tooltip or description or title)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(13)
        icon = LineIcon(symbol, "ChoiceIcon")
        icon.setFixedSize(34, 34)
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(icon)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("ChoiceTitle")
        heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy.addWidget(heading)
        if description:
            detail = QLabel(description)
            detail.setObjectName("ChoiceDescription")
            detail.setWordWrap(True)
            detail.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            copy.addWidget(detail)
        row.addLayout(copy, 1)

        self.radio = QFrame()
        self.radio.setObjectName("ChoiceRadio")
        self.radio.setProperty("accent", accent)
        self.radio.setProperty("selected", False)
        self.radio.setFixedSize(17, 17)
        self.radio.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.radio)
        self.toggled.connect(self._show_selection)
        self._show_selection(self.isChecked())

    def _show_selection(self, selected):
        self.radio.setProperty("selected", selected)
        self.radio.style().unpolish(self.radio)
        self.radio.style().polish(self.radio)
        self.radio.update()
