"""Small shared Qt widgets used by both wallet modes."""

from PySide6.QtCore import QByteArray, Qt, QRectF, QSize, Signal
from .vendor.lifehash import LifeHash, LifeHashVersion
from PySide6.QtGui import QImage, QColor, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QTableWidget, QVBoxLayout, QWidget


_ICONS = {
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "back": '<path d="m14 6-6 6 6 6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "arrow-right": '<path d="M4 12h15m-6-6 6 6-6 6"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 4v3"/>',
    "copy": '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
    "switch": '<path d="M4 7h15m-4-4 4 4-4 4M20 17H5m4-4-4 4 4 4"/>',
    "dice": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h.01M16 8h.01M12 12h.01M8 16h.01M16 16h.01"/>',
    "warning": '<path d="M10.2 4.5 2.9 17a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.8 4.5a2.1 2.1 0 0 0-3.6 0ZM12 9v4m0 3h.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "download": '<path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
    "refresh": '<path d="M20 10a8 8 0 0 0-14-3L3 10m0-6v6h6M4 14a8 8 0 0 0 14 3l3-3m0 6v-6h-6"/>',
    "file": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Zm0 0v6h6M8 13h8m-8 4h5"/>',
    "shield-check": '<path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
    "bitcoin": '<path d="M9 6h5a3 3 0 0 1 0 6H9m0 0h6a3 3 0 0 1 0 6H9V6M7 6h2m-2 12h2M11 3v3m3-3v3m-3 12v3m3-3v3"/>',
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
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.6 9a2.5 2.5 0 1 1 4.3 1.8c-1.2 1.1-1.9 1.4-1.9 3.2M12 17h.01"/>',
    "dark": '<path d="M12 3a9 9 0 1 0 0 18V3Z"/><circle cx="12" cy="12" r="9"/>',
    "light": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
}
_ICON_ALIASES = {
    "▦": "scan", "▣": "wallet", "⚙": "settings", "⌘": "policy",
    "↓": "receive", "⇧": "activity", "❄": "cold", "◉": "node",
    "＋": "new", "↻": "import",
    "i": "help", "◐": "dark", "☼": "light",
}


def fixed_font(size):
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(size)
    return font


class EmptyTable(QTableWidget):
    """A regular table with a quiet message when there are no visible rows."""

    def __init__(self, rows=0, columns=0, parent=None, *, empty_title="No entries yet", empty_hint=""):
        super().__init__(rows, columns, parent)
        self._empty = QWidget(self.viewport())
        self._empty.setObjectName("TableEmptyState")
        self._empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        content = QVBoxLayout(self._empty)
        content.setContentsMargins(20, 20, 20, 20)
        content.setSpacing(8)
        content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = self._empty_title = QLabel(empty_title)
        title.setObjectName("Heading")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(title)
        hint = self._empty_hint = QLabel(empty_hint)
        hint.setObjectName("EmptyHint")
        hint.setTextFormat(Qt.TextFormat.PlainText)
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setVisible(bool(empty_hint))
        content.addWidget(hint)
        self.model().rowsInserted.connect(self.update_empty_state)
        self.model().rowsRemoved.connect(self.update_empty_state)
        self.model().modelReset.connect(self.update_empty_state)
        self.update_empty_state()

    def set_empty_message(self, title, hint=""):
        self._empty_title.setText(title)
        self._empty_hint.setText(hint)
        self._empty_hint.setVisible(bool(hint))
        self._empty.updateGeometry()

    def update_empty_state(self, *_args):
        self._empty.setVisible(not any(not self.isRowHidden(row) for row in range(self.rowCount())))
        self._empty.setGeometry(self.viewport().rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_empty"):
            self._empty.setGeometry(self.viewport().rect())


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

    def set_glyph(self, glyph):
        self._paths = _ICONS.get(_ICON_ALIASES.get(glyph, glyph))
        self.setText("" if self._paths else glyph)
        self.update()

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


class ComboBox(QComboBox):
    """A native selector with a visible, theme-aware dropdown indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chevron = LineIcon("chevron-down", "ToolbarIcon", inset=0, stroke_width=1.7)
        self._chevron.setParent(self)
        self._chevron.setGeometry(max(0, self.width() - 29), (self.height() - 16) // 2, 16, 16)
        self._chevron.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_chevron"):
            self._chevron.setGeometry(max(0, self.width() - 29), (self.height() - 16) // 2, 16, 16)


class FingerprintMark(QWidget):
    """LifeHash v2 of the public wallet policy, without theme recoloring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._identity = None
        self.setMinimumSize(88, 88)
        self.setAccessibleName("Wallet LifeHash")
        self.setToolTip("LifeHash v2 of this wallet's public descriptor. This recognition aid does not replace checking the full wallet policy.")

    def sizeHint(self):
        return QSize(144, 144)

    def set_fingerprint(self, fingerprint):
        self.set_identity(str(fingerprint))

    def set_identity(self, identity):
        data = identity if isinstance(identity, bytes) else str(identity).encode("utf-8")
        if data == self._identity:
            return
        result = LifeHash.make_from(data, version=LifeHashVersion.version2, module_size=1, has_alpha=False)
        self._image = QImage(bytes(result.colors), result.width, result.height,
                             result.width * 3, QImage.Format.Format_RGB888).copy()
        self._identity = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        size = min(self.width(), self.height())
        margin = max(5, size // 18)
        rectangle = QRectF((self.width() - size) / 2 + margin,
                           (self.height() - size) / 2 + margin,
                           size - 2 * margin, size - 2 * margin)
        painter.fillRect(rectangle, QColor("white"))
        painter.drawImage(rectangle, self._image)
        painter.end()


class ScanIllustration(QWidget):
    """Static scanner artwork; decorative shapes contain no encoded QR data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ScanIllustration")
        self.setFixedSize(152, 152)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName("Decorative scanner illustration")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.width() / 152, self.height() / 152)
        accent = self.palette().color(QPalette.ColorRole.WindowText)
        faint, line = QColor(accent), QColor(accent)
        faint.setAlpha(8)
        line.setAlpha(35)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(faint)
        painter.drawEllipse(QRectF(5, 5, 142, 142))
        painter.setPen(QPen(line, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(18, 18, 116, 116))
        painter.save()
        painter.translate(76, 76)
        painter.rotate(-8)
        painter.setPen(QPen(line, 1.2))
        painter.setBrush(faint)
        painter.drawRoundedRect(QRectF(-32, -40, 64, 80), 10, 10)
        for y, width in ((-17, 34), (-5, 26), (7, 34), (19, 18)):
            painter.drawLine(-17, y, -17 + width, y)
        painter.restore()
        painter.setPen(QPen(accent, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        corners = QPainterPath()
        for x, y, sx, sy in ((31, 35, 1, 1), (121, 35, -1, 1), (31, 117, 1, -1), (121, 117, -1, -1)):
            corners.moveTo(x, y + sy * 14)
            corners.lineTo(x, y + sy * 4)
            corners.quadTo(x, y, x + sx * 4, y)
            corners.lineTo(x + sx * 14, y)
        painter.drawPath(corners)
        scan = QColor(accent)
        scan.setAlpha(160)
        painter.setPen(QPen(scan, 1.5))
        painter.drawLine(24, 76, 128, 76)
        painter.end()


class ActionRow(QFrame):
    clicked = Signal()

    def __init__(self, symbol, title, description, *, primary=False, tooltip="", icon_key=None, hero=False):
        super().__init__()
        self.setObjectName("ActionPrimary" if primary else "ActionRow")
        self.setProperty("hero", hero)
        self.setProperty("pressed", False)
        self._pointer_down = False
        self._key_down = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description or tooltip)
        self.setToolTip(tooltip or description)
        row = QHBoxLayout(self)
        if hero:
            row.setContentsMargins(26, 24, 20, 24)
        else:
            row.setContentsMargins(18, 15, 18, 15)
        row.setSpacing(16)
        self.icon = LineIcon(icon_key or symbol, "BlueIcon", inset=11 if hero else 9)
        icon_size = 48 if hero else 42
        self.icon.setFixedSize(icon_size, icon_size)
        self.arrow = LineIcon("arrow-right" if hero else "chevron-right", "ActionChevron", inset=0, stroke_width=1.8)
        self.arrow.setFixedSize(20, 20)
        if not hero:
            row.addWidget(self.icon)
        copy = QVBoxLayout()
        copy.setSpacing(9 if hero else 4)
        copy.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        if hero:
            copy.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignLeft)
            copy.addStretch()
        self.title_label = QLabel(title)
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setWordWrap(True)
        self.title_label.setObjectName("ActionTitle")
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy.addWidget(self.title_label)
        if description:
            detail = QLabel(description)
            detail.setTextFormat(Qt.TextFormat.PlainText)
            detail.setObjectName("ActionDescription")
            detail.setWordWrap(True)
            detail.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            copy.addWidget(detail)
        row.addLayout(copy, 1)
        if hero:
            self.illustration = ScanIllustration()
            row.addWidget(self.illustration, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.arrow, 0, Qt.AlignmentFlag.AlignTop if hero else Qt.AlignmentFlag.AlignVCenter)

    def _set_pressed(self, pressed):
        self.setProperty("pressed", pressed)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._pointer_down = True
            self._set_pressed(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pointer_down:
            self._set_pressed(self.rect().contains(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pointer_down:
            self._pointer_down = False
            self._set_pressed(False)
            event.accept()
            if self.isEnabled() and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Space):
            if not event.isAutoRepeat():
                self._key_down = True
                self._set_pressed(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Space):
            if not event.isAutoRepeat() and self._key_down:
                self._key_down = False
                self._set_pressed(False)
                self.clicked.emit()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._pointer_down = False
        self._key_down = False
        self._set_pressed(False)
        super().focusOutEvent(event)


class _Button(QPushButton):
    """Explicit keyboard activation without becoming a dialog's implicit action."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAutoDefault(False)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.isAutoRepeat():
                self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class ChoiceRow(_Button):
    """Compact selectable row matching the wallet mode and setup screens."""

    def __init__(self, symbol, title, description="", *, accent="green", tooltip="", card=False):
        super().__init__()
        self.setObjectName("ModeCard" if card else "ChoiceRow")
        self.setProperty("accent", accent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
        if description:
            self.setAccessibleDescription(description)
        self.setToolTip(tooltip or description or title)

        row = QVBoxLayout(self) if card else QHBoxLayout(self)
        if card:
            row.setContentsMargins(24, 24, 24, 24)
        else:
            row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(13)
        icon = LineIcon(symbol, "ChoiceIcon")
        icon_size = 52 if card else 38
        icon.setFixedSize(icon_size, icon_size)
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.radio = QFrame()
        self.radio.setObjectName("ChoiceRadio")
        self.radio.setProperty("accent", accent)
        self.radio.setProperty("selected", False)
        self.radio.setFixedSize(17, 17)
        self.radio.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if card:
            top = QHBoxLayout()
            top.addWidget(icon)
            top.addStretch()
            top.addWidget(self.radio, 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(top)
            row.addSpacing(20)
        else:
            row.addWidget(icon)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        heading = QLabel(title)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        heading.setObjectName("ChoiceTitle")
        heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy.addWidget(heading)
        if description:
            detail = QLabel(description)
            detail.setTextFormat(Qt.TextFormat.PlainText)
            detail.setObjectName("ChoiceDescription")
            detail.setWordWrap(True)
            detail.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            copy.addWidget(detail)
        row.addLayout(copy, 0 if card else 1)
        if not card:
            row.addWidget(self.radio)
        self.toggled.connect(self._show_selection)
        self._show_selection(self.isChecked())

    def _show_selection(self, selected):
        self.radio.setProperty("selected", selected)
        self.radio.style().unpolish(self.radio)
        self.radio.style().polish(self.radio)
        self.radio.update()


class IconButton(_Button):
    """Small icon-and-label button for the desktop header."""

    def __init__(self, glyph, text, callback, *, tooltip=""):
        super().__init__()
        self.setObjectName("ToolbarButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(text)
        self.setToolTip(tooltip or text)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(6)
        self.icon = LineIcon(glyph, "ToolbarIcon", stroke_width=2.1, inset=0)
        self.icon.setFixedSize(16, 16)
        row.addWidget(self.icon)
        self.caption = QLabel(text)
        self.caption.setObjectName("ToolbarText")
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.caption)
        self.clicked.connect(callback)

    def set_caption(self, text):
        self.caption.setText(text)
        self.setAccessibleName(text)
        self.updateGeometry()

    def sizeHint(self):
        return super().sizeHint().expandedTo(self.layout().sizeHint())

    def minimumSizeHint(self):
        return self.sizeHint()

    def set_glyph(self, glyph):
        self.icon.set_glyph(glyph)
