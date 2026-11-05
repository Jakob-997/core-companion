"""Compact, shared Qt theme for the cold signer and online wallet."""

_STYLE = """
QMainWindow, QDialog, QWidget#Page, QWidget#OnboardingPage, QWidget#OnlinePage { background: @page@; }
QWidget { color: @text@; font-size: 13px; }
QWidget#PageContent, QWidget#TableEmptyState { background: transparent; }
QFrame#HeaderDivider, QFrame#IdentityRule { background: @border@; border: 0; max-height: 1px; }
QMenuBar { background: @surface@; padding: 3px 12px; border-bottom: 1px solid @border@; }
QMenuBar::item, QMenu::item { padding: 6px 10px; }
QMenuBar::item:selected, QMenu::item:selected { background: @blue-soft@; color: @blue@; }
QMenu, QWidget#Card, QFrame#Card, QWidget#Surface, QFrame#Surface,
QWidget#FormPanel, QFrame#FormPanel, QFrame#IdentityPanel, QFrame#KPI,
QFrame#CoreConnectionPanel { background: @surface@; border: 1px solid @border@; border-radius: 9px; }
QWidget#SubtlePanel, QFrame#SubtlePanel, QFrame#InfoStrip { background: @surface-2@; border: 1px solid @border@; border-radius: 8px; }
QLabel#Brand { font-size: 15px; font-weight: 700; }
QLabel#Mark { background: @blue-soft@; color: @blue@; border: 1px solid @blue-border@; border-radius: 8px; font-size: 18px; font-weight: 700; }
QLabel#Title, QLabel#CompactTitle, QLabel#EmptyTitle { font-size: 25px; font-weight: 680; }
QLabel#HeroTitle { font-size: 30px; font-weight: 700; }
QLabel#Heading, QLabel#PanelHeading, QLabel#FormTitle { font-size: 17px; font-weight: 650; }
QLabel#Eyebrow, QLabel#SectionLabel, QLabel#StepLabel { color: @muted@; font-size: 10px; font-weight: 700; }
QLabel#Muted, QLabel#PageDescription, QLabel#PanelDescription, QLabel#FormHint,
QLabel#FooterNote, QLabel#EmptyHint, QLabel#IdentityMeta, QLabel#ChoiceDescription,
QLabel#ActionDescription, QLabel#MetricLabel { color: @muted@; }
QLabel#FieldLabel, QLabel#OutputRole, QLabel#OutputIndex { color: @muted@; font-size: 11px; font-weight: 650; }
QLabel#Value, QLabel#ActionTitle, QLabel#ChoiceTitle, QLabel#NoticeTitle { font-weight: 650; }
QLabel#Hash, QLabel#Fingerprint, QLabel#CodeValue { color: @blue@; font-family: monospace; font-size: 13px; }
QLabel#Fingerprint[hero="true"] { font-size: 22px; }
QLabel#CoreStatus { font-size: 14px; font-weight: 700; }
QLabel#CoreStatus[state="connected"], QLabel#Verification[verified="true"] { color: @accent-strong@; }
QLabel#CoreStatus[state="error"], QLabel#Verification[verified="false"] { color: @red@; }
QLabel#DevNotice { background: @warning-soft@; color: @warning@; border: 1px solid @warning-border@; border-radius: 6px; padding: 7px 10px; font-weight: 650; }
QLabel#Badge, QLabel#SecurePill { background: @accent-soft@; color: @accent-strong@; padding: 4px 8px; border-radius: 8px; font-size: 11px; font-weight: 650; }
QLabel#ColdBadge, QLabel#HeaderMode { background: @blue-soft@; color: @blue@; padding: 4px 8px; border-radius: 8px; font-size: 11px; font-weight: 650; }
QLabel#HeaderMode[mode="online"] { background: @red-soft@; color: @red@; }
QLabel#Balance, QLabel#BalanceHero, QLabel#MetricValue { font-size: 29px; font-weight: 650; }
QLabel#SecondaryBalance { color: @muted@; font-size: 19px; }
QLabel#KPIValue { font-size: 16px; font-weight: 650; }
QPushButton { min-height: 36px; padding: 0 13px; border: 1px solid @border@; border-radius: 7px; background: @surface@; color: @text@; font-weight: 600; }
QPushButton:hover { background: @surface-2@; border-color: @blue-border@; }
QPushButton:focus { border-color: @blue@; }
QPushButton:pressed { background: @blue-soft@; }
QPushButton:disabled { color: @muted@; background: @surface-2@; }
QPushButton#Primary, QMainWindow#OnlineNode QPushButton#ColdContinue { background: @blue@; border-color: @blue@; color: @button-text@; }
QPushButton#Primary:hover, QMainWindow#OnlineNode QPushButton#ColdContinue:hover { background: @blue@; }
QWidget#OnlinePage QPushButton#Primary, QMainWindow#OnlineNode QPushButton#OnlineContinue,
QDialog#OnlineDialog QPushButton#Primary { background: @red@; border-color: @red@; color: @button-text@; }
QWidget#OnlinePage QPushButton#Primary:hover, QMainWindow#OnlineNode QPushButton#OnlineContinue:hover,
QDialog#OnlineDialog QPushButton#Primary:hover { background: @red@; }
QPushButton#Primary:disabled, QWidget#OnlinePage QPushButton#Primary:disabled,
QMainWindow#OnlineNode QPushButton#ColdContinue:disabled, QMainWindow#OnlineNode QPushButton#OnlineContinue:disabled {
    background: @surface-2@; border-color: @border@; color: @muted@;
}
QPushButton#ChoiceRow, QPushButton#ModeCard { min-height: 62px; border: 1px solid @border@; border-radius: 8px; background: @surface@; color: @text@; text-align: left; }
QPushButton#ChoiceRow:hover, QPushButton#ModeCard:hover { background: @surface-2@; border-color: @blue-border@; }
QPushButton#ChoiceRow:checked[accent="green"], QPushButton#ModeCard:checked[accent="green"] { border: 2px solid @accent@; background: @accent-soft@; }
QPushButton#ChoiceRow:checked[accent="blue"], QPushButton#ModeCard:checked[accent="blue"] { border: 2px solid @blue@; background: @blue-soft@; }
QPushButton#ChoiceRow:checked[accent="red"], QPushButton#ModeCard:checked[accent="red"] { border: 2px solid @red@; background: @red-soft@; }
QLabel#ChoiceIcon, QLabel#BlueIcon { background: @blue-soft@; color: @blue@; border-radius: 7px; }
QPushButton[accent="red"] QLabel#ChoiceIcon, QMainWindow#OnlineNode QLabel#BlueIcon { background: @red-soft@; color: @red@; }
QFrame#ChoiceRadio { border: 1px solid @muted@; border-radius: 8px; }
QFrame#ChoiceRadio[accent="green"][selected="true"] { border: 5px solid @accent@; }
QFrame#ChoiceRadio[accent="blue"][selected="true"] { border: 5px solid @blue@; }
QFrame#ChoiceRadio[accent="red"][selected="true"] { border: 5px solid @red@; }
QPushButton#Quiet, QPushButton#ToolbarButton { min-height: 30px; padding: 0 8px; border-color: transparent; background: transparent; color: @muted@; }
QPushButton#Quiet:hover, QPushButton#ToolbarButton:hover { color: @text@; background: @surface-2@; }
QPushButton#Quiet[active="true"], QPushButton#ToolbarButton[active="true"] { color: @blue@; background: @blue-soft@; }
QLabel#ToolbarText, QLabel#ToolbarIcon, QLabel#ActionChevron { color: @muted@; }
QFrame#ActionRow, QFrame#ActionPrimary { min-height: 58px; border: 1px solid @border@; border-radius: 8px; background: @surface@; }
QFrame#ActionRow:hover, QFrame#ActionPrimary:hover { border-color: @blue-border@; }
QFrame#ActionPrimary, QFrame#ColdNotice { background: @blue-soft@; border: 1px solid @blue-border@; border-radius: 8px; }
QLabel#IdentityName { font-size: 21px; font-weight: 650; }
QWidget#IdentityMark { background: @surface-2@; border: 1px solid @border@; border-radius: 8px; }
QLabel#IdentityTile { background: @border@; border-radius: 1px; }
QLabel#IdentityTile[lit="true"] { background: @blue@; }
QFrame#IdentityHero { background: @blue-soft@; border: 1px solid @blue-border@; border-radius: 10px; }
QFrame#IdentityHero QLabel#IdentityName, QFrame#IdentityHero QLabel#Fingerprint { color: @blue@; }
QFrame#ScanTarget { background: @surface-2@; border: 1px dashed @blue-border@; border-radius: 8px; }
QLabel#QR, QWidget#QRPanel, QFrame#QRPanel { background: white; border: 1px solid @border@; border-radius: 8px; }
QFrame#VerificationPanel[state="error"], QLabel#ReviewWarning { background: @red-soft@; border: 1px solid @red-border@; border-radius: 8px; }
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QTableWidget { background: @surface@; color: @text@; border: 1px solid @border@; border-radius: 7px; padding: 7px 9px; selection-background-color: @blue-soft@; selection-color: @text@; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus { border-color: @blue@; }
QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled, QSpinBox:disabled { color: @muted@; background: @surface-2@; }
QComboBox { min-width: 130px; }
QComboBox::drop-down { border: 0; width: 22px; }
QSpinBox#PolicyNumber { padding-left: 16px; padding-right: 32px; }
QCheckBox { spacing: 7px; }
QGroupBox { margin-top: 9px; padding: 9px; border: 1px solid @border@; border-radius: 7px; background: @surface@; }
QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0 4px; color: @muted@; }
QProgressBar { border: 0; border-radius: 4px; background: @surface-2@; }
QProgressBar::chunk { border-radius: 4px; background: @blue@; }
QTableWidget { gridline-color: transparent; alternate-background-color: @surface-2@; }
QTableWidget::item { padding: 5px 7px; border-bottom: 1px solid @border@; }
QHeaderView::section { background: @surface-2@; color: @muted@; border: 0; padding: 7px 9px; font-size: 10px; font-weight: 700; }
QStatusBar { background: @surface@; color: @muted@; border-top: 1px solid @border@; padding: 3px 8px; }
QScrollBar:vertical { background: @page@; width: 9px; }
QScrollBar::handle:vertical { background: @border@; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: @text@; background: @surface@; border: 1px solid @border@; padding: 6px 8px; }
"""

_PALETTES = {
    False: {
        "page": "#f3f6f8", "surface": "#ffffff", "surface-2": "#f7f9fb",
        "text": "#18232d", "muted": "#586775", "border": "#d5dfe6", "button-text": "#ffffff",
        "accent": "#16745c", "accent-strong": "#105c49", "accent-soft": "#e5f4ee",
        "blue": "#185fa8", "blue-soft": "#e8f2fd", "blue-border": "#adc8e4",
        "red": "#bd433d", "red-soft": "#fff0ed", "red-border": "#e4b7b4",
        "warning": "#754900", "warning-soft": "#fff1dc", "warning-border": "#e7bd82",
    },
    True: {
        "page": "#11171c", "surface": "#192129", "surface-2": "#202a33",
        "text": "#edf3f7", "muted": "#aab6c0", "border": "#36434e", "button-text": "#11171c",
        "accent": "#65c9a0", "accent-strong": "#84ddb8", "accent-soft": "#1e3830",
        "blue": "#83b9ee", "blue-soft": "#203447", "blue-border": "#3e617e",
        "red": "#ff9e94", "red-soft": "#3d282a", "red-border": "#75474a",
        "warning": "#f1c27b", "warning-soft": "#3b3020", "warning-border": "#735b35",
    },
}


def stylesheet(dark=False):
    """Return the one shared light or dark style sheet."""
    style = _STYLE
    for name, value in _PALETTES[bool(dark)].items():
        style = style.replace(f"@{name}@", value)
    return style

