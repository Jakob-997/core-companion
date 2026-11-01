"""Shared Qt theme matching the Core Companion desktop design."""


_STYLE = """
QMainWindow, QDialog { background: @page@; }
QWidget { color: @text@; font-family: sans-serif; font-size: 13px; }
QWidget#Page { background: @page@; }
QWidget#OnboardingPage { background: @page@; }
QWidget#OnlinePage { background: @page@; }
QWidget#PageContent { background: transparent; }
QMenuBar { background: @surface@; padding: 4px 14px; border-bottom: 1px solid @border@; }
QMenuBar::item { padding: 6px 10px; }
QMenuBar::item:selected, QMenu::item:selected { background: @accent-soft@; color: @accent-strong@; }
QMenu { background: @surface@; padding: 6px; border: 1px solid @border@; }
QMenu::item { padding: 7px 24px; }
QWidget#Card, QFrame#Card { background: @surface@; border: 1px solid @border@; border-radius: 10px; }
QLabel#Brand { color: @text@; font-size: 14px; font-weight: 650; }
QLabel#Mark { background: @blue-soft@; color: @blue@; border: 1px solid @blue-border@; border-radius: 9px; font-size: 19px; font-weight: 700; }
QLabel#Title { color: @text@; font-size: 27px; font-weight: 620; }
QLabel#Heading { color: @text@; font-size: 19px; font-weight: 600; }
QLabel#Eyebrow { color: @muted@; font-size: 10px; font-weight: 650; letter-spacing: 1px; }
QLabel#Muted { color: @muted@; }
QLabel#Hash { color: @blue@; font-family: monospace; font-size: 13px; }
QLabel#DevNotice { background: #fff1dc; color: #754900; border: 1px solid #e7bd82; border-radius: 7px; padding: 8px 11px; font-weight: 650; }
QLabel#Badge { background: @accent-soft@; color: @accent-strong@; padding: 5px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; }
QLabel#Balance { color: @text@; font-size: 29px; font-weight: 650; }
QLabel#SecondaryBalance { color: @muted@; font-size: 20px; font-weight: 550; }
QPushButton { min-height: 38px; padding: 0 15px; border: 1px solid @border@; border-radius: 7px; background: @surface@; color: @text@; font-weight: 600; }
QPushButton:hover { background: @surface-2@; border-color: @accent@; }
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
QPushButton#ChoiceRow { min-height: 78px; border: 1px solid @border@; border-radius: 7px; background: @surface@; color: @text@; text-align: left; font-weight: 500; }
QPushButton#ChoiceRow:hover { border-color: @accent@; background: @surface-2@; }
QPushButton#ChoiceRow:checked[accent="green"] { border: 2px solid @accent@; background: @accent-soft@; }
QPushButton#ChoiceRow:checked[accent="blue"] { border: 2px solid @blue@; background: @blue-soft@; }
QPushButton#ChoiceRow:checked[accent="red"] { border: 2px solid @red@; background: @red-soft@; }
QLabel#ChoiceIcon { background: @surface-2@; color: @accent-strong@; border-radius: 7px; font-size: 17px; font-weight: 650; }
QPushButton#ChoiceRow[accent="blue"] QLabel#ChoiceIcon { background: @blue-soft@; color: @blue@; }
QPushButton#ChoiceRow[accent="red"] QLabel#ChoiceIcon { background: @red-soft@; color: @red@; }
QLabel#ChoiceTitle { color: @text@; font-size: 13px; font-weight: 620; }
QLabel#ChoiceDescription { color: @muted@; font-size: 11px; font-weight: 400; }
QLabel#ChoiceRadio { color: @muted@; font-size: 16px; }
QFrame#ChoiceDivider { border: 0; border-top: 1px solid @border@; min-height: 1px; max-height: 1px; }
QPushButton#ChoiceRow:checked[accent="green"] QLabel#ChoiceRadio { color: @accent-strong@; }
QPushButton#ChoiceRow:checked[accent="blue"] QLabel#ChoiceRadio { color: @blue@; }
QPushButton#ChoiceRow:checked[accent="red"] QLabel#ChoiceRadio { color: @red@; }
QMainWindow#OnlineNode QPushButton#ColdContinue { background: @blue@; border-color: @blue@; color: white; }
QMainWindow#OnlineNode QPushButton#ColdContinue:hover { background: @blue@; }
QFrame#KPI { background: @surface@; border: 1px solid @border@; border-radius: 9px; }
QLabel#KPIValue { color: @text@; font-size: 17px; font-weight: 650; }
QProgressBar { border: 0; border-radius: 4px; background: @surface-2@; }
QProgressBar::chunk { border-radius: 4px; background: @red@; }
QPushButton#Quiet { border-color: transparent; background: transparent; color: @muted@; }
QPushButton#Quiet:hover { color: @text@; background: @surface-2@; }
QPushButton#Quiet[active="true"] { color: @blue@; background: @blue-soft@; }
QFrame#ActionRow, QFrame#ActionPrimary { min-height: 74px; border: 1px solid @border@; border-radius: 9px; background: @surface@; }
QFrame#ActionRow:hover { background: @surface-2@; border-color: @blue-border@; }
QFrame#ActionPrimary { background: @blue-soft@; border-color: @blue-border@; }
QFrame#ActionPrimary:hover { border-color: @blue@; }
QDialog#ColdSigner QFrame#ActionPrimary { background: @blue-soft@; border-color: @blue-border@; }
QDialog#ColdSigner QFrame#ActionPrimary:hover { border-color: @blue@; }
QDialog#ColdSigner QLabel#BlueIcon { background: @blue-soft@; color: @blue@; }
QFrame#ColdNotice { background: @blue-soft@; border: 1px solid @blue-border@; border-radius: 8px; }
QLabel#ActionTitle { color: @text@; font-size: 14px; font-weight: 620; }
QLabel#BlueIcon { background: @blue-soft@; color: @blue@; border-radius: 8px; font-size: 18px; font-weight: 650; }
QFrame#IdentityPanel { background: @surface@; border: 1px solid @border@; border-radius: 10px; }
QWidget#IdentityMark { background: @surface-2@; border: 1px solid @border@; border-radius: 7px; }
QLabel#IdentityTile { background: @border@; border-radius: 1px; }
QLabel#IdentityTile[lit="true"] { background: @blue@; }
QLabel#IdentityName { color: @text@; font-size: 17px; font-weight: 650; }
QLabel#ScanTarget { background: @surface-2@; color: @blue@; border: 1px dashed @blue-border@; border-radius: 9px; font-size: 50px; }
QLabel#QR { background: white; border: 1px solid @border@; border-radius: 8px; }
QLabel#Verification[verified="true"] { color: #1e7049; font-weight: 650; }
QLabel#Verification[verified="false"] { color: #b0413e; font-weight: 650; }
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QTableWidget { background: @surface@; color: @text@; border: 1px solid @border@; border-radius: 7px; padding: 8px 10px; selection-background-color: @accent-soft@; selection-color: @text@; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus { border-color: @accent@; }
QComboBox { min-width: 150px; }
QComboBox::drop-down { border: 0; width: 22px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QCheckBox::indicator:checked { background: @accent@; border: 1px solid @accent-strong@; border-radius: 4px; }
QGroupBox { margin-top: 10px; padding: 10px; border: 1px solid @border@; border-radius: 8px; background: @surface@; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: @muted@; }
QTabWidget::pane { border: 1px solid @border@; border-radius: 8px; background: @surface@; }
QTabBar::tab { padding: 10px 18px; color: @muted@; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: @accent-strong@; border-bottom-color: @accent@; }
QTableWidget { gridline-color: @border@; alternate-background-color: @surface-2@; selection-background-color: @accent-soft@; }
QHeaderView::section { background: @surface-2@; color: @muted@; border: 0; border-bottom: 1px solid @border@; padding: 9px 11px; font-size: 10px; font-weight: 650; }
QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid @border@; }
QStatusBar { background: @surface@; color: @muted@; border-top: 1px solid @border@; padding: 4px 10px; }
QStatusBar::item { border: 0; }
QScrollBar:vertical { background: @page@; width: 9px; }
QScrollBar::handle:vertical { background: @border@; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

_PALETTES = {
    False: {
        "page": "#f2f5f3", "surface": "#ffffff", "surface-2": "#f8faf8",
        "text": "#202a25", "muted": "#64716a", "border": "#dce4de",
        "accent": "#286b50", "accent-strong": "#1f5a41", "accent-soft": "#e8f3ed",
        "blue": "#185a9f", "blue-soft": "#e7f1ff", "blue-border": "#a8c4e8",
        "red": "#a13d3a", "red-soft": "#fff0ef", "red-border": "#e0aaa8",
    },
    True: {
        "page": "#151b18", "surface": "#1e2621", "surface-2": "#252f29",
        "text": "#e4ece7", "muted": "#a0aea5", "border": "#39473e",
        "accent": "#8dd2ae", "accent-strong": "#a7dfc0", "accent-soft": "#2a4034",
        "blue": "#8bbce8", "blue-soft": "#25384a", "blue-border": "#41617d",
        "red": "#eea19e", "red-soft": "#3b2627", "red-border": "#744544",
    },
}


def stylesheet(dark=False):
    style = _STYLE
    for name, value in _PALETTES[bool(dark)].items():
        style = style.replace(f"@{name}@", value)
    return style
