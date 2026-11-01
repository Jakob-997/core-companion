"""Shared Qt theme matching the Core Companion desktop design."""


_STYLE = """
QMainWindow, QDialog { background: @page@; }
QWidget { color: @text@; font-family: "Cantarell"; font-size: 14px; }
QWidget#Page { background: @page@; }
QWidget#OnboardingPage { background: @page@; }
QWidget#OnlinePage { background: @page@; }
QWidget#PageContent { background: transparent; }
QFrame#HeaderDivider { background: @border@; border: 0; }
QMenuBar { background: @surface@; padding: 4px 14px; border-bottom: 1px solid @border@; }
QMenuBar::item { padding: 6px 10px; }
QMenuBar::item:selected, QMenu::item:selected { background: @accent-soft@; color: @accent-strong@; }
QMenu { background: @surface@; padding: 6px; border: 1px solid @border@; }
QMenu::item { padding: 7px 24px; }
QWidget#Card, QFrame#Card { background: @surface@; border: 1px solid @border@; border-radius: 12px; }
QLabel#Brand { color: @text@; font-size: 15px; font-weight: 700; }
QLabel#Mark { background: @blue-soft@; color: @blue@; border: 1px solid @blue-border@; border-radius: 10px; font-size: 19px; font-weight: 700; }
QLabel#Title { color: @text@; font-size: 28px; font-weight: 680; }
QLabel#Heading { color: @text@; font-size: 18px; font-weight: 650; }
QLabel#Eyebrow { color: @muted@; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#Muted { color: @muted@; font-size: 12px; }
QLabel#Hash { color: @blue@; font-family: monospace; font-size: 13px; }
QLabel#DevNotice { background: #fff1dc; color: #754900; border: 1px solid #e7bd82; border-radius: 7px; padding: 8px 11px; font-weight: 650; }
QLabel#Badge { background: @accent-soft@; color: @accent-strong@; padding: 5px 10px; border-radius: 999px; font-size: 11px; font-weight: 650; }
QLabel#ColdBadge { background: @blue-soft@; color: @blue@; padding: 5px 10px; border-radius: 999px; font-size: 11px; font-weight: 650; }
QLabel#Balance { color: @text@; font-size: 29px; font-weight: 650; }
QLabel#SecondaryBalance { color: @muted@; font-size: 20px; font-weight: 550; }
QPushButton { min-height: 40px; padding: 0 15px; border: 1px solid @border@; border-radius: 8px; background: @surface@; color: @text@; font-weight: 600; }
QPushButton:hover { background: @surface-2@; border-color: @accent@; }
QPushButton:focus { border-color: @accent@; }
QPushButton:pressed { background: @accent-soft@; }
QPushButton:disabled { color: @muted@; background: @surface-2@; }
QPushButton#Primary { background: @accent@; border-color: @accent-strong@; color: white; }
QPushButton#Primary:hover { background: @accent-strong@; }
QDialog#ColdSigner QPushButton#Primary { background: @blue@; border-color: @blue@; color: white; }
QDialog#ColdSigner QPushButton#Primary:hover { background: @blue@; border-color: @blue@; }
QWidget#OnlinePage QPushButton#Primary { background: @red@; border-color: @red@; color: white; }
QWidget#OnlinePage QPushButton#Primary:hover { background: @red@; }
QMainWindow#OnlineNode QPushButton#OnlineContinue { background: @red@; border-color: @red@; color: white; }
QMainWindow#OnlineNode QPushButton#OnlineContinue:hover { background: @red@; }
QMainWindow#OnlineNode QFrame#ActionPrimary { background: @red-soft@; border-color: @red-border@; }
QMainWindow#OnlineNode QFrame#ActionPrimary:hover { border-color: @red@; }
QMainWindow#OnlineNode QLabel#BlueIcon { background: @red-soft@; color: @red@; }
QPushButton#ChoiceRow { min-height: 70px; border: 1px solid @border@; border-radius: 10px; background: @surface@; color: @text@; text-align: left; font-weight: 500; }
QPushButton#ChoiceRow:hover { border-color: @accent@; background: @surface-2@; }
QPushButton#ChoiceRow:checked[accent="green"] { border: 2px solid @accent@; background: @accent-soft@; }
QPushButton#ChoiceRow:checked[accent="blue"] { border: 2px solid @blue@; background: @blue-soft@; }
QPushButton#ChoiceRow:checked[accent="red"] { border: 2px solid @red@; background: @red-soft@; }
QLabel#ChoiceIcon { background: @surface-2@; color: @accent-strong@; border-radius: 9px; font-size: 17px; font-weight: 650; }
QPushButton#ChoiceRow[accent="blue"] QLabel#ChoiceIcon { background: @blue-soft@; color: @blue@; }
QPushButton#ChoiceRow[accent="red"] QLabel#ChoiceIcon { background: @red-soft@; color: @red@; }
QLabel#ChoiceTitle { color: @text@; font-size: 13px; font-weight: 620; }
QLabel#ChoiceDescription { color: @muted@; font-size: 11px; font-weight: 400; }
QFrame#ChoiceDivider { border: 0; border-top: 1px solid @border@; min-height: 1px; max-height: 1px; }
QFrame#ChoiceRadio { border: 1px solid @muted@; border-radius: 9px; background: transparent; }
QFrame#ChoiceRadio[accent="green"][selected="true"] { border: 5px solid @accent@; background: @surface@; }
QFrame#ChoiceRadio[accent="blue"][selected="true"] { border: 5px solid @blue@; background: @surface@; }
QFrame#ChoiceRadio[accent="red"][selected="true"] { border: 5px solid @red@; background: @surface@; }
QMainWindow#OnlineNode QPushButton#ColdContinue { background: @blue@; border-color: @blue@; color: white; }
QMainWindow#OnlineNode QPushButton#ColdContinue:hover { background: @blue@; }
QFrame#KPI { background: @surface@; border: 1px solid @border@; border-radius: 10px; }
QLabel#KPIValue { color: @text@; font-size: 17px; font-weight: 650; }
QProgressBar { border: 0; border-radius: 4px; background: @surface-2@; }
QProgressBar::chunk { border-radius: 4px; background: @red@; }
QPushButton#Quiet { border-color: transparent; background: transparent; color: @muted@; }
QPushButton#Quiet:hover { color: @text@; background: @surface-2@; }
QPushButton#Quiet[active="true"] { color: @blue@; background: @blue-soft@; }
QPushButton#ToolbarButton { min-height: 32px; padding: 0 9px; border-color: transparent; border-radius: 7px; background: transparent; color: @muted@; font-weight: 550; }
QPushButton#ToolbarButton:hover { border-color: @border@; background: @surface-2@; color: @text@; }
QPushButton#ToolbarButton:pressed, QPushButton#ToolbarButton[active="true"] { border-color: @blue-border@; background: @blue-soft@; color: @blue@; }
QLabel#ToolbarIcon { color: @muted@; }
QLabel#ToolbarText { color: @muted@; font-size: 12px; }
QPushButton#ToolbarButton:hover QLabel#ToolbarText, QPushButton#ToolbarButton[active="true"] QLabel#ToolbarText { color: @text@; }
QToolTip { color: @text@; background: @surface@; border: 1px solid @border@; padding: 6px 8px; }
QFrame#ActionRow, QFrame#ActionPrimary { min-height: 66px; border: 1px solid @border@; border-radius: 10px; background: @surface@; }
QFrame#ActionRow:hover { background: @surface-2@; border-color: @blue-border@; }
QFrame#ActionPrimary { background: @blue-soft@; border-color: @blue-border@; }
QFrame#ActionPrimary:hover { border-color: @blue@; }
QDialog#ColdSigner QFrame#ActionPrimary { background: @blue-soft@; border-color: @blue-border@; }
QDialog#ColdSigner QFrame#ActionPrimary:hover { border-color: @blue@; }
QDialog#ColdSigner QLabel#BlueIcon { background: @blue-soft@; color: @blue@; }
QFrame#ColdNotice { background: @blue-soft@; border: 1px solid @blue-border@; border-radius: 10px; }
QLabel#ColdNoticeIcon { color: @blue@; }
QLabel#NoticeTitle { color: @text@; font-size: 14px; font-weight: 620; }
QLabel#ActionTitle { color: @text@; font-size: 14px; font-weight: 620; }
QLabel#BlueIcon { background: @blue-soft@; color: @blue@; border-radius: 8px; font-size: 18px; font-weight: 650; }
QFrame#IdentityPanel { background: @surface@; border: 1px solid @border@; border-radius: 12px; }
QWidget#IdentityMark { background: @surface-2@; border: 1px solid @border@; border-radius: 9px; }
QLabel#IdentityTile { background: @border@; border-radius: 1px; }
QLabel#IdentityTile[lit="true"] { background: @blue@; }
QLabel#IdentityName { color: @text@; font-size: 18px; font-weight: 630; }
QLabel#IdentityMeta { color: @muted@; font-size: 12px; }
QFrame#ScanTarget { background: @surface-2@; border: 1px dashed @blue-border@; border-radius: 10px; }
QLabel#ScanGlyph { color: @blue@; }
QLabel#QR { background: white; border: 1px solid @border@; border-radius: 8px; }
QLabel#Verification[verified="true"] { color: @accent-strong@; font-weight: 700; }
QLabel#Verification[verified="false"] { color: @red@; font-weight: 700; }
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QTableWidget { background: @surface@; color: @text@; border: 1px solid @border@; border-radius: 8px; padding: 8px 10px; selection-background-color: @accent-soft@; selection-color: @text@; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus { border-color: @accent@; }
QComboBox { min-width: 150px; }
QComboBox::drop-down { border: 0; width: 22px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid @border@; border-radius: 4px; background: @surface@; }
QCheckBox::indicator:checked { background: @accent@; border: 1px solid @accent-strong@; border-radius: 4px; }
QGroupBox { margin-top: 10px; padding: 10px; border: 1px solid @border@; border-radius: 8px; background: @surface@; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: @muted@; }
QTabWidget::pane { border: 1px solid @border@; border-radius: 10px; background: @surface@; }
QTabBar::tab { padding: 10px 18px; color: @muted@; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: @accent-strong@; border-bottom-color: @accent@; }
QTableWidget { gridline-color: transparent; alternate-background-color: @surface-2@; selection-background-color: @accent-soft@; }
QTableWidget::item:selected { color: @text@; background: @accent-soft@; }
QHeaderView::section { background: @surface-2@; color: @muted@; border: 0; border-bottom: 1px solid @border@; padding: 9px 11px; font-size: 10px; font-weight: 700; }
QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid @border@; }
QStatusBar { background: @surface@; color: @muted@; border-top: 1px solid @border@; padding: 4px 10px; }
QStatusBar::item { border: 0; }
QScrollBar:vertical { background: @page@; width: 9px; }
QScrollBar::handle:vertical { background: @border@; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

_PALETTES = {
    False: {
        "page": "#f3f6f8", "surface": "#ffffff", "surface-2": "#f7f9fb",
        "text": "#18232d", "muted": "#586775", "border": "#d5dfe6",
        "accent": "#16745c", "accent-strong": "#105c49", "accent-soft": "#e5f4ee",
        "blue": "#185fa8", "blue-soft": "#e8f2fd", "blue-border": "#adc8e4",
        "red": "#bd433d", "red-soft": "#fff0ed", "red-border": "#e4b7b4",
    },
    True: {
        "page": "#11171c", "surface": "#192129", "surface-2": "#202a33",
        "text": "#edf3f7", "muted": "#aab6c0", "border": "#36434e",
        "accent": "#65c9a0", "accent-strong": "#84ddb8", "accent-soft": "#1e3830",
        "blue": "#83b9ee", "blue-soft": "#203447", "blue-border": "#3e617e",
        "red": "#ff9e94", "red-soft": "#3d282a", "red-border": "#75474a",
    },
}


def stylesheet(dark=False):
    style = _STYLE
    for name, value in _PALETTES[bool(dark)].items():
        style = style.replace(f"@{name}@", value)
    return style
