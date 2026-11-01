"""Small shared Qt widgets used by both wallet modes."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


class ActionRow(QFrame):
    clicked = Signal()

    def __init__(self, symbol, title, description, *, primary=False, tooltip=""):
        super().__init__()
        self.setObjectName("ActionPrimary" if primary else "ActionRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(tooltip or description)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(13)
        icon = QLabel(symbol)
        icon.setObjectName("BlueIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(36, 36)
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(icon)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("ActionTitle")
        heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy.addWidget(heading)
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
