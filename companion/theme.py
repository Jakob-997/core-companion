"""Shared native Qt design tokens and styles for both wallet modes."""


_STYLE = """
QMainWindow, QDialog { background: @page@; }
QWidget { color: @text@; font-size: 14px; }
QWidget#Page, QWidget#OnboardingPage, QWidget#OnlinePage { background: @page@; }
QWidget#PageContent { background: transparent; }
QFrame#HeaderDivider { background: @border@; border: 0; }
QMenuBar { background: @page@; padding: 3px 14px; border-bottom: 1px solid @border@; }
QMenuBar::item { padding: 6px 10px; border-radius: 5px; }
QMenuBar::item:selected, QMenu::item:selected { background: @blue-soft@; color: @blue@; }
QMenu { background: @surface@; padding: 6px; border: 1px solid @border@; border-radius: 8px; }
QMenu::item { padding: 8px 26px; border-radius: 4px; }
QWidget#Card, QFrame#Card, QWidget#Surface, QFrame#Surface {
    background: @surface@; border: 1px solid @border@; border-radius: 16px;
}
QWidget#SubtlePanel, QFrame#SubtlePanel {
    background: @surface-2@; border: 1px solid @border@; border-radius: 12px;
}
QLabel#Brand { color: @text@; font-size: 16px; font-weight: 700; letter-spacing: -0.4px; }
QLabel#Mark { background: @blue@; color: @button-text@; border: 0; border-radius: 12px; }
QLabel#Title { color: @text@; font-size: 30px; font-weight: 700; letter-spacing: -0.8px; }
QLabel#HeroTitle { color: @text@; font-size: 36px; font-weight: 700; letter-spacing: -1.1px; }
QLabel#Heading, QLabel#PanelHeading { color: @text@; font-size: 18px; font-weight: 650; letter-spacing: -0.25px; }
QLabel#Eyebrow, QLabel#SectionLabel {
    color: @muted@; font-size: 11px; font-weight: 650; letter-spacing: 1.2px;
}
QLabel#Muted, QLabel#PanelDescription { color: @muted@; font-size: 12px; }
QLabel#PageDescription { color: @muted@; font-size: 14px; }
QLabel#FooterNote { color: @muted@; font-size: 11px; }
QLabel#Hash, QLabel#Fingerprint { color: @blue@; font-family: monospace; font-size: 13px; font-weight: 600; letter-spacing: 1px; }
QLabel#Fingerprint[hero="true"] { font-size: 26px; letter-spacing: 1.4px; }
QLabel#DevNotice {
    background: @warning-soft@; color: @warning@; border: 1px solid @warning-border@;
    border-radius: 8px; padding: 8px 12px; font-size: 12px; font-weight: 600;
}
QLabel#Badge, QLabel#SecurePill {
    background: @accent-soft@; color: @accent-strong@; padding: 5px 10px;
    border-radius: 10px; font-size: 11px; font-weight: 600;
}
QLabel#ColdBadge, QLabel#HeaderMode {
    background: @blue-soft@; color: @blue@; padding: 5px 11px;
    border-radius: 10px; font-size: 11px; font-weight: 600;
}
QLabel#HeaderMode[mode="online"] { background: @red-soft@; color: @red@; }
QLabel#Balance, QLabel#MetricValue { color: @text@; font-size: 38px; font-weight: 650; letter-spacing: -1px; }
QLabel#MetricLabel { color: @muted@; font-size: 11px; font-weight: 600; letter-spacing: 0.5px; }
QLabel#SecondaryBalance { color: @muted@; font-size: 20px; font-weight: 500; }
QPushButton {
    min-height: 40px; padding: 0 18px; border: 1px solid @border@; border-radius: 9px;
    background: @surface@; color: @text@; font-weight: 600;
}
QPushButton:hover { background: @surface-2@; border-color: @border-strong@; }
QPushButton:focus { border: 1px solid @blue@; }
QPushButton:pressed { background: @blue-soft@; border-color: @blue@; }
QPushButton:disabled { color: @disabled@; background: @surface-2@; border-color: @border@; }
QPushButton#Primary, QMainWindow#OnlineNode QPushButton#ColdContinue {
    background: @blue@; border-color: @blue@; color: @button-text@;
}
QPushButton#Primary:hover, QMainWindow#OnlineNode QPushButton#ColdContinue:hover { background: @blue-hover@; border-color: @blue-hover@; }
QPushButton#Primary:focus, QMainWindow#OnlineNode QPushButton#ColdContinue:focus { border: 2px solid @blue-focus@; }
QPushButton#Primary:pressed { background: @blue-hover@; }
QWidget#OnlinePage QPushButton#Primary, QMainWindow#OnlineNode QPushButton#OnlineContinue {
    background: @red@; border-color: @red@; color: @button-text@;
}
QWidget#OnlinePage QPushButton#Primary:hover, QMainWindow#OnlineNode QPushButton#OnlineContinue:hover { background: @red-hover@; border-color: @red-hover@; }
QPushButton#Primary:disabled, QWidget#OnlinePage QPushButton#Primary:disabled,
QMainWindow#OnlineNode QPushButton#ColdContinue:disabled, QMainWindow#OnlineNode QPushButton#OnlineContinue:disabled {
    background: @surface-2@; border-color: @border@; color: @disabled@;
}
QPushButton#ChoiceRow, QPushButton#ModeCard {
    min-height: 74px; border: 1px solid @border@; border-radius: 12px;
    background: @surface@; color: @text@; text-align: left; font-weight: 500;
}
QPushButton#ModeCard { min-height: 204px; border-radius: 16px; }
QPushButton#ChoiceRow:hover, QPushButton#ModeCard:hover { border-color: @border-strong@; background: @surface-2@; }
QPushButton#ChoiceRow:focus, QPushButton#ModeCard:focus { border-color: @blue@; }
QPushButton#ChoiceRow:checked[accent="green"], QPushButton#ModeCard:checked[accent="green"] { border: 2px solid @accent@; background: @accent-soft@; }
QPushButton#ChoiceRow:checked[accent="blue"], QPushButton#ModeCard:checked[accent="blue"] { border: 2px solid @blue@; background: @blue-soft@; }
QPushButton#ChoiceRow:checked[accent="red"], QPushButton#ModeCard:checked[accent="red"] { border: 2px solid @red@; background: @red-soft@; }
QLabel#ChoiceIcon { background: @surface-2@; color: @blue@; border-radius: 10px; }
QPushButton[accent="blue"] QLabel#ChoiceIcon { background: @blue-soft@; color: @blue@; }
QPushButton[accent="red"] QLabel#ChoiceIcon { background: @red-soft@; color: @red@; }
QLabel#ChoiceTitle { color: @text@; font-size: 14px; font-weight: 650; }
QLabel#ChoiceDescription { color: @muted@; font-size: 12px; font-weight: 400; }
QPushButton#ModeCard QLabel#ChoiceTitle { font-size: 21px; letter-spacing: -0.5px; }
QPushButton#ModeCard QLabel#ChoiceDescription { font-size: 13px; }
QFrame#ChoiceDivider { border: 0; border-top: 1px solid @border@; min-height: 1px; max-height: 1px; }
QFrame#ChoiceRadio { border: 1px solid @border-strong@; border-radius: 8px; background: @surface@; }
QFrame#ChoiceRadio[accent="green"][selected="true"] { border: 5px solid @accent@; background: @surface@; }
QFrame#ChoiceRadio[accent="blue"][selected="true"] { border: 5px solid @blue@; background: @surface@; }
QFrame#ChoiceRadio[accent="red"][selected="true"] { border: 5px solid @red@; background: @surface@; }
QFrame#KPI { background: @surface@; border: 1px solid @border@; border-radius: 12px; }
QLabel#KPIValue { color: @text@; font-size: 22px; font-weight: 650; letter-spacing: -0.5px; }
QProgressBar { border: 0; border-radius: 3px; background: @border@; }
QProgressBar::chunk { border-radius: 3px; background: @red@; }
QPushButton#Quiet { border-color: transparent; background: transparent; color: @muted@; }
QPushButton#Quiet:hover { color: @text@; background: @surface-2@; }
QPushButton#Quiet:focus { border-color: @blue@; }
QPushButton#Quiet[active="true"] { color: @blue@; background: @blue-soft@; }
QPushButton#ToolbarButton {
    min-height: 32px; padding: 0 6px; border-color: transparent; border-radius: 7px;
    background: transparent; color: @muted@; font-weight: 500;
}
QPushButton#ToolbarButton:hover { border-color: @border@; background: @surface@; color: @text@; }
QPushButton#ToolbarButton:focus { border-color: @blue@; }
QPushButton#ToolbarButton:pressed, QPushButton#ToolbarButton[active="true"] { border-color: @blue-border@; background: @blue-soft@; color: @blue@; }
QLabel#ToolbarIcon, QLabel#ToolbarText { color: @muted@; font-size: 12px; }
QPushButton#ToolbarButton:hover QLabel, QPushButton#ToolbarButton[active="true"] QLabel { color: @text@; }
QToolTip { color: @text@; background: @surface@; border: 1px solid @border-strong@; padding: 8px 10px; font-size: 12px; }
QFrame#ActionRow, QFrame#ActionPrimary {
    min-height: 78px; border: 1px solid @border@; border-radius: 12px; background: @surface@;
}
QFrame#ActionRow:hover { background: @surface-2@; border-color: @blue-border@; }
QFrame#ActionPrimary { background: @blue-soft@; border-color: @blue-border@; }
QFrame#ActionPrimary:hover { background: @blue-soft@; border-color: @blue@; }
QFrame#ActionRow:focus, QFrame#ActionPrimary:focus { border: 2px solid @blue@; }
QFrame#ActionRow[pressed="true"], QFrame#ActionPrimary[pressed="true"] { background: @blue-soft@; border-color: @blue@; }
QFrame#ActionRow:disabled, QFrame#ActionPrimary:disabled { background: @surface-2@; border-color: @border@; }
QLabel:disabled { color: @disabled@; }
QFrame#ActionRow[hero="true"], QFrame#ActionPrimary[hero="true"] {
    min-height: 190px; border-radius: 18px; border-color: @blue-border@;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @surface@, stop:1 @hero-surface@);
}
QFrame#ActionPrimary[hero="true"]:hover { border-color: @blue@; }
QFrame#ActionPrimary[hero="true"]:focus { border: 2px solid @blue@; }
QFrame#ActionPrimary[hero="true"][pressed="true"] { background: @blue-soft@; }
QFrame[hero="true"] QLabel#ActionTitle { font-size: 26px; font-weight: 650; letter-spacing: -0.6px; }
QFrame[hero="true"] QLabel#ActionDescription { font-size: 13px; }
QWidget#ScanIllustration { color: @blue@; background: transparent; }
QWidget#OnlinePage QWidget#ScanIllustration { color: @red@; }
QMainWindow#OnlineNode QFrame#ActionPrimary { background: @red-soft@; border-color: @red-border@; }
QMainWindow#OnlineNode QFrame#ActionPrimary:hover { border-color: @red@; }
QMainWindow#OnlineNode QLabel#BlueIcon { background: @red-soft@; color: @red@; }
QFrame#ColdNotice, QFrame#InfoStrip {
    background: @blue-soft@; border: 1px solid @blue-border@; border-radius: 12px;
}
QLabel#InfoStrip {
    background: @blue-soft@; color: @blue@; border: 1px solid @blue-border@;
    border-radius: 8px; padding: 12px; font-size: 12px;
}
QLabel#ColdNoticeIcon { color: @blue@; }
QLabel#NoticeTitle { color: @text@; font-size: 14px; font-weight: 600; }
QLabel#ActionTitle { color: @text@; font-size: 16px; font-weight: 650; letter-spacing: -0.2px; }
QLabel#ActionDescription { color: @muted@; font-size: 12px; }
QLabel#ActionChevron { color: @muted@; }
QLabel#BlueIcon { background: @surface-2@; color: @blue@; border-radius: 10px; }
QFrame#ActionPrimary QLabel#BlueIcon { background: @surface@; color: @blue@; }
QMainWindow#OnlineNode QFrame#ActionPrimary QLabel#BlueIcon { color: @red@; }
QFrame#IdentityPanel { background: @surface@; border: 1px solid @border@; border-radius: 16px; }
QFrame#IdentityHero, QWidget#IdentityHero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #183963, stop:0.55 #102a4e, stop:1 #0b203e);
    border: 1px solid #284b76; border-radius: 20px;
}
QWidget#IdentityMark { background: @surface@; border: 1px solid @blue-border@; border-radius: 12px; }
QLabel#IdentityTile { background: @blue-soft@; border-radius: 2px; }
QLabel#IdentityTile[lit="true"] { background: @blue@; }
QLabel#IdentityName { color: @text@; font-size: 32px; font-weight: 650; letter-spacing: -0.9px; }
QLabel#IdentityMeta { color: @muted@; font-size: 13px; }
QFrame#IdentityHero QLabel#IdentityName { color: #f2f7ff; }
QFrame#IdentityHero QLabel#IdentityMeta, QFrame#IdentityHero QLabel#SectionLabel,
QFrame#IdentityHero QLabel#IdentityEyebrow { color: #a3bcdc; }
QFrame#IdentityHero QLabel#Fingerprint { color: #c2ddff; }
QFrame#IdentityHero QLabel#ColdBadge, QLabel#IdentityChip {
    color: #d3e6ff; background: #24456d; border: 1px solid #345681; border-radius: 9px;
    font-size: 11px; font-weight: 600; padding: 5px 10px;
}
QFrame#IdentityHero QPushButton#ToolbarButton { color: #d3e6ff; background: transparent; border-color: transparent; }
QFrame#IdentityHero QPushButton#ToolbarButton:hover { background: #24456d; border-color: #345681; }
QFrame#IdentityHero QPushButton#ToolbarButton:focus { border-color: #9fc7ff; }
QFrame#IdentityHero QLabel#ToolbarIcon, QFrame#IdentityHero QLabel#ToolbarText { color: #d3e6ff; }
QFrame#IdentityRule { background: #345475; border: 0; max-height: 1px; }
QLabel#ActionKicker { color: @blue@; font-size: 11px; font-weight: 650; letter-spacing: 1px; }
QFrame#ScanTarget { background: @surface-2@; border: 1px dashed @blue-border@; border-radius: 14px; }
QLabel#ScanGlyph { color: @blue@; }
QLabel#QR { background: white; border: 1px solid @border@; border-radius: 12px; }
QLabel#Verification[verified="true"] { color: @accent-strong@; font-weight: 650; }
QLabel#Verification[verified="false"] { color: @red@; font-weight: 650; }
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QTableWidget {
    background: @surface@; color: @text@; border: 1px solid @border@; border-radius: 8px;
    padding: 9px 12px; selection-background-color: @blue-soft@; selection-color: @text@;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: @border-strong@; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus { border-color: @blue@; }
QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled, QSpinBox:disabled { color: @disabled@; background: @surface-2@; }
QComboBox { min-width: 150px; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox QAbstractItemView { background: @surface@; color: @text@; selection-background-color: @blue-soft@; selection-color: @text@; border: 1px solid @border@; padding: 4px; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QGroupBox { margin-top: 12px; padding: 16px; border: 1px solid @border@; border-radius: 12px; background: @surface@; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: @muted@; font-size: 12px; }
QTabWidget::pane { border: 1px solid @border@; border-radius: 12px; background: @surface@; }
QTabBar::tab { padding: 11px 20px; color: @muted@; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: @blue@; border-bottom-color: @blue@; }
QTableWidget { gridline-color: transparent; alternate-background-color: @surface-2@; selection-background-color: @blue-soft@; padding: 0; }
QTableWidget#EmbeddedTable { border: 0; border-radius: 0; }
QTableWidget::item:selected { color: @text@; background: @blue-soft@; }
QHeaderView::section {
    background: @surface-2@; color: @muted@; border: 0; border-bottom: 1px solid @border@;
    padding: 12px 14px; font-size: 10px; font-weight: 650; letter-spacing: 0.7px;
}
QTableWidget::item { padding: 8px 12px; border-bottom: 1px solid @border@; }
QStatusBar { background: @page@; color: @muted@; border-top: 1px solid @border@; padding: 5px 14px; font-size: 11px; }
QStatusBar::item { border: 0; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: @border-strong@; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QFrame#WorkflowBar { background: @surface@; border: 1px solid @border@; border-radius: 10px; }
QLabel#StepLabel { color: @muted@; font-size: 11px; padding: 8px 10px; }
QLabel#StepLabel[state="current"] { color: @blue@; background: @blue-soft@; font-weight: 650; border-radius: 6px; }
QLabel#StepLabel[state="complete"] { color: @text@; }
QLabel#StepLabel[state="upcoming"] { color: @muted@; }
QFrame#WordTile { background: @surface-2@; border: 1px solid @border@; border-radius: 9px; }
QWidget#WordTile { background: @surface-2@; border: 1px solid @border@; border-radius: 9px; }
QLabel#WordNumber { color: @muted@; font-size: 11px; font-family: monospace; }
QLabel#WordText { color: @text@; font-size: 18px; font-family: monospace; font-weight: 600; }
QLabel#ReviewAmount { color: @text@; font-size: 34px; font-weight: 650; letter-spacing: -1px; }
QLabel#ReviewAddress { color: @text@; font-family: monospace; font-size: 14px; }
QLabel#OutputRole { color: @blue@; background: @blue-soft@; font-size: 11px; font-weight: 600; padding: 4px 8px; border-radius: 6px; }
QLabel#OutputRole[kind="change"] { color: @accent-strong@; background: @accent-soft@; }
QLabel#OutputRole[kind="own"] { color: @blue@; background: @blue-soft@; }
QLabel#OutputIndex { color: @muted@; font-size: 11px; font-family: monospace; }
QLabel#OutputAmount { color: @text@; font-size: 24px; font-weight: 650; letter-spacing: -0.6px; }
QLabel#OutputIcon { color: @blue@; background: @surface-2@; border-radius: 8px; }
QFrame#ReviewWarning, QLabel#ReviewWarning {
    background: @warning-soft@; color: @warning@; border: 1px solid @warning-border@; border-radius: 9px;
}
QLabel#CoreStatus { color: @text@; font-size: 15px; font-weight: 650; }
QLabel#CoreStatus[state="connected"] { color: @accent-strong@; }
QLabel#CoreStatus[state="error"] { color: @red@; }
QFrame#WelcomePanel { background: @surface@; border: 1px solid @border@; border-radius: 18px; }
QLabel#WelcomeMark { background: @blue@; color: @button-text@; border-radius: 18px; }
QWidget#WelcomeIdentity, QFrame#WelcomeIdentity {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #193d6b, stop:0.55 #112e53, stop:1 #0b213f);
    border: 1px solid #2d507b; border-radius: 22px;
}
QLabel#WelcomeEyebrow { color: #abc6e7; font-size: 11px; font-weight: 600; letter-spacing: 1.4px; }
QLabel#WelcomeTitle { color: #f6f9ff; font-size: 38px; font-weight: 700; letter-spacing: -1px; }
QLabel#WelcomeDetail { color: #c3d5ed; font-size: 14px; }
QLabel#WelcomeBrand { color: #d7e8ff; font-size: 12px; font-weight: 600; }
QLabel#WelcomeArtwork { color: #9cc8ff; }
QFrame#BalanceHero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @surface@, stop:1 @balance-surface@);
    border: 1px solid @red-border@; border-radius: 18px;
}
QLabel#DashboardAmount, QLabel#HeroAmount { color: @text@; font-size: 40px; font-weight: 650; letter-spacing: -1.4px; }
"""

_PALETTES = {
    False: {
        "page": "#f2f5f8", "surface": "#ffffff", "surface-2": "#f7f9fc", "hero": "#edf3fd",
        "hero-surface": "#f1f6ff", "balance-surface": "#fff8f6",
        "text": "#172a40", "muted": "#5f7289", "disabled": "#91a0b1",
        "border": "#dce4ee", "border-strong": "#b4c3d4", "button-text": "#ffffff",
        "accent": "#23785d", "accent-strong": "#176548", "accent-soft": "#e6f4ed",
        "blue": "#2664cf", "blue-hover": "#194da9", "blue-focus": "#8db7ff", "blue-soft": "#eaf1fc", "blue-border": "#c6d8f3",
        "red": "#bf4d44", "red-hover": "#a13b34", "red-soft": "#fcf0ee", "red-border": "#efd0cb",
        "warning": "#86580f", "warning-soft": "#fff7e8", "warning-border": "#eddbb3",
    },
    True: {
        "page": "#0f1723", "surface": "#182436", "surface-2": "#1c2b3e", "hero": "#192b46",
        "hero-surface": "#1c304b", "balance-surface": "#2c252f",
        "text": "#edf3fc", "muted": "#a5b3c7", "disabled": "#74849a",
        "border": "#2b3b50", "border-strong": "#465c78", "button-text": "#102039",
        "accent": "#79d2ae", "accent-strong": "#93e2c1", "accent-soft": "#203a34",
        "blue": "#9ac3ff", "blue-hover": "#b6d4ff", "blue-focus": "#dceaff", "blue-soft": "#203651", "blue-border": "#3b577b",
        "red": "#f8a69a", "red-hover": "#ffc4ba", "red-soft": "#3a292e", "red-border": "#69464c",
        "warning": "#efc57d", "warning-soft": "#332c20", "warning-border": "#615039",
    },
}


def stylesheet(dark=False):
    style = _STYLE
    for name, value in _PALETTES[bool(dark)].items():
        style = style.replace(f"@{name}@", value)
    return style
