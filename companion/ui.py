"""Qt desktop views; Core access remains in wallet.py and rpc.py."""
import argparse
import base64
import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
from PySide6.QtCore import Qt, QProcess, QTimer, QEvent, QSettings, QProcessEnvironment
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget, QDialog,
    QFormLayout, QPlainTextEdit, QFrame, QProgressBar, QToolTip, QScrollArea,
    QStackedWidget, QSizePolicy)
from PySide6.QtWidgets import QMessageBox, QCheckBox, QFileDialog
from .qr import qr_pixmap
from qrcode.exceptions import DataOverflowError
from .scanner import QRScanner
from .rpc import CoreError, CoreRPC
from .wallet import WalletService, btc
from .linux_cold import ColdSetupError, ColdSystemSession, _system_tool
from .permanent_airgap import PermanentAirgap
from .network_privacy import core_tor_arguments, assert_core_tor
from .tor import TorSession
from .theme import stylesheet
from .widgets import ActionRow, ChoiceRow, ComboBox, EmptyTable, IconButton, LineIcon, ScanIllustration, fixed_font
from . import DEVELOPMENT_BUILD, __version__

MANAGED_RPC_PORT = 8332
PRUNE_TARGET_MIB = 10000

def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    return widget

def button(text, action, primary=False):
    widget = QPushButton(text)
    widget.setAutoDefault(False)
    if primary:
        widget.setObjectName("Primary")
    widget.clicked.connect(action)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def default_cookie_path():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "Bitcoin"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Bitcoin"
    else:
        base = Path.home() / ".bitcoin"
    return base / ".cookie"


def companion_data_dir():
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    data_home = Path(xdg_data_home) if xdg_data_home and Path(xdg_data_home).is_absolute() else Path.home() / ".local" / "share"
    return data_home / "core-companion"


def managed_node_dir():
    return companion_data_dir() / "bitcoin-node"


def page_layout(top=20, bottom=16, name="Page"):
    page = QWidget()
    page.setObjectName(name)
    layout = QVBoxLayout(page)
    layout.setContentsMargins(32, top, 32, bottom)
    layout.setSpacing(16)
    return page, layout

class App(QMainWindow):
    def __init__(self, dev_keep_network=False):
        super().__init__()
        self.setObjectName("OnlineNode")
        self.setWindowTitle("Core Companion")
        self.resize(1280, 850)
        self.setMinimumSize(980, 680)
        self.dark_mode = False
        self.help_mode = False
        self.mode_choice = None
        self.connection_purpose = "welcome"
        self.cold_notice_previous = 1
        self.setStyleSheet(stylesheet())
        self.service = None
        self.busy = False
        self.events = queue.Queue()
        self.skip = 0
        self.rows = []
        self.cold_session = None
        self.cold_process = None
        self.cold_process_group = None
        self.cold_session_id = None
        self.cold_temp_path = None
        self.cold_restoring = False
        self.dev_keep_network = bool(dev_keep_network)
        self.permanent_cold = PermanentAirgap.is_committed()
        self.cold_required = self.permanent_cold or (not self.dev_keep_network and PermanentAirgap.saved_wallets_exist())
        self.isolation_timer = QTimer(self)
        self.isolation_timer.setInterval(2000)
        self.isolation_timer.timeout.connect(self._check_cold_isolation)
        self.core_download_process = None
        self.core_download_stderr = ""
        self.downloaded_bitcoind = None
        self.core_download_closing = False
        self.core_download_cancelled = False
        self.core_cookie_path = None
        self.connection_fallback = False
        self.pending_cold_start = False
        self.managed_core_process = None
        self.managed_node_tor_proxy = None
        self.managed_rpc_port = MANAGED_RPC_PORT
        self.tor_enabled = QSettings("CoreCompanion", "CoreCompanion").value("network/torOnly", True, type=bool)
        self.tor_pending = None
        self.tor_install_process = None
        self.tor_install_output = ""
        self.tor = TorSession(self)
        self.tor.ready.connect(self._tor_ready)
        self.tor.progress.connect(lambda value: self._set_core_status(f"Connecting to Tor · {value}%"))
        self.tor.unavailable.connect(self._tor_unavailable)
        self.node_start_timer = QTimer(self)
        self.node_start_timer.setInterval(1200)
        self.node_start_timer.timeout.connect(self._poll_managed_node)
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(5000)
        self.sync_timer.timeout.connect(self.refresh_sync_status)
        self._menus()
        self._layout()
        self._connection_dialog()
        self._install_help_targets()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._drain)
        self.timer.start(40)
        self.statusBar().showMessage("Bitcoin Core connection is local to this computer")
        self._set_core_status("Choose privacy, then connect or download Core.")
        if self.cold_required:
            self._lock_cold_installation()
            self.mode_choice = "cold"
            self._select_mode("cold")
            self.tabs.setCurrentIndex(7)
    def _menus(self):
        menu = self.menuBar().addMenu("Wallet")
        self.wallet_menu = menu
        for text, callback in [
            ("Welcome", lambda: self.tabs.setCurrentIndex(0)),
            ("Choose wallet mode", lambda: self.tabs.setCurrentIndex(1)),
            ("Wallet home", lambda: self.tabs.setCurrentIndex(2)),
            ("Advanced connection…", self.show_connection),
            ("Disconnect", self.disconnect),
            ("About Core Companion", self.about),
            ("Close", self.close),
        ]:
            action = QAction(text, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.menuBar().hide()

    def _layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 12, 24, 8)
        root.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        mark = LineIcon("bitcoin", "Mark", stroke_width=1.9, inset=4)
        mark.setFixedSize(38, 38)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.global_back = IconButton("back", "Back", self._go_back)
        toolbar.addWidget(self.global_back)
        toolbar.addWidget(mark)
        toolbar.addWidget(label("Core Companion", "Brand"))
        self.mode_indicator = label("ONLINE NODE", "HeaderMode")
        self.mode_indicator.setProperty("mode", "online")
        toolbar.addSpacing(12)
        toolbar.addWidget(self.mode_indicator)
        self.mode_indicator.hide()
        toolbar.addStretch()
        self.help_button = IconButton(
            "i", "Help", self._toggle_help_mode,
            tooltip="Turn on instant explanations. Hover over a control to see what it does.",
        )
        toolbar.addWidget(self.help_button)
        self.theme_button = IconButton("dark", "Dark mode", self._toggle_theme)
        toolbar.addWidget(self.theme_button)
        toolbar.addWidget(IconButton("node", "Connection", self.show_connection))
        menu_button = QPushButton("&Wallet")
        menu_button.setObjectName("ToolbarButton")
        menu_button.setMenu(self.wallet_menu)
        menu_button.setToolTip("Open wallet navigation, connection options, and application information.")
        toolbar.addWidget(menu_button)
        root.addLayout(toolbar)
        divider = QFrame()
        divider.setObjectName("HeaderDivider")
        divider.setFixedHeight(1)
        root.addWidget(divider)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().hide()
        root.addWidget(self.tabs, 1)
        self._welcome()
        self._mode_page()
        self._online_home()
        self._history()
        self._receive()
        self._addresses()
        self._tools()
        self._cold_network_page()
        self._send()
        self.network = label("○  Offline", "Muted")
        self.statusBar().addPermanentWidget(self.network)
        self.cold_button_top = self.mode_continue
        if sys.platform != "linux":
            self.cold_choice.setEnabled(False)
            self.cold_choice.setToolTip("The cold signer is available on Linux in this first release.")
        self.tabs.setCurrentIndex(0)
        self.tabs.currentChanged.connect(lambda index: self.mode_indicator.setVisible(2 <= index <= 6 or index == 8))
        self.tabs.currentChanged.connect(lambda index: self.global_back.setVisible(index not in (0, 2)))
        self.global_back.hide()

    def _welcome(self):
        page, layout = page_layout(20, 20, "OnboardingPage")
        layout.addStretch(1)
        content = QHBoxLayout()
        content.setSpacing(24)
        introduction_panel = QFrame()
        introduction_panel.setObjectName("WelcomeIdentity")
        introduction_panel.setMinimumHeight(420)
        introduction = QVBoxLayout(introduction_panel)
        introduction.setContentsMargins(32, 30, 32, 30)
        introduction.setSpacing(18)
        introduction.addWidget(label("CORE COMPANION", "WelcomeEyebrow"))
        core_icon = LineIcon("node", "WelcomeArtwork", stroke_width=1.25, inset=8)
        core_icon.setFixedSize(100, 100)
        introduction.addWidget(core_icon)
        title = label("Welcome to\nCore Companion", "WelcomeTitle")
        title.setWordWrap(True)
        introduction.addWidget(title)
        intro = label("Cold storage.\nYour own watch-only node.", "WelcomeDetail")
        intro.setWordWrap(True)
        introduction.addWidget(intro)
        introduction.addStretch()
        introduction.addWidget(label("BUILT AROUND BITCOIN CORE", "WelcomeBrand"))
        content.addWidget(introduction_panel, 5)
        card = QFrame()
        card.setObjectName("Surface")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card_layout.setSpacing(8)
        card_layout.addWidget(label("01  /  LOCAL CONNECTION", "SectionLabel"))
        card_layout.addWidget(label("Bitcoin Core", "Title"))
        status_panel = QFrame()
        status_panel.setObjectName("SubtlePanel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(10, 10, 10, 10)
        status_layout.setSpacing(8)
        self.core_status = label("Checking for Bitcoin Core…", "CoreStatus")
        self.core_status.setWordWrap(True)
        self.core_status.setMinimumHeight(36)
        self.core_status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        status_layout.addWidget(self.core_status)
        card_layout.addWidget(status_panel)
        self.tor_choice = QCheckBox("Tor only (recommended)")
        self.tor_choice.setChecked(self.tor_enabled)
        self.tor_choice.setToolTip("Route Core downloads, signing-key downloads and blockchain sync through Tor, with no direct fallback.")
        self.tor_choice.toggled.connect(self._privacy_toggled)
        card_layout.addWidget(self.tor_choice)
        privacy_note = label("Downloads and sync stop if Tor disconnects.", "FormHint")
        privacy_note.setWordWrap(True)
        card_layout.addWidget(privacy_note)
        card_layout.addWidget(button("Connect to Bitcoin Core", self.connect, True))
        self.download_button = button("Download && verify Bitcoin Core", self.download_bitcoin_core)
        self.download_button.setToolTip(
            "Downloads Core and its pinned signer keys, verifies the release, then installs it."
        )
        card_layout.addWidget(self.download_button)
        download_status = QHBoxLayout()
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 0)
        self.download_progress.setTextVisible(False)
        self.download_progress.setFixedHeight(7)
        self.download_progress.hide()
        download_status.addWidget(self.download_progress, 1)
        self.cancel_download_button = button("Cancel", self.cancel_core_download)
        self.cancel_download_button.hide()
        download_status.addWidget(self.cancel_download_button)
        card_layout.addLayout(download_status)
        advanced = QHBoxLayout()
        advanced_button = button("Advanced connection settings…", self.show_connection)
        advanced_button.setObjectName("Quiet")
        advanced.addWidget(advanced_button)
        advanced.addStretch()
        card_layout.addLayout(advanced)
        card_layout.addStretch()
        content.addWidget(card, 6)
        layout.addLayout(content)
        layout.addStretch(1)
        continue_row = QHBoxLayout()
        continue_row.addWidget(label("Need a hand? Hover over a control, or turn on Help.", "FooterNote"))
        continue_row.addStretch()
        continue_row.addWidget(button("Choose wallet mode  →", lambda: self.tabs.setCurrentIndex(1), True))
        layout.addLayout(continue_row)
        self.tabs.addTab(page, "Welcome")

    def _set_core_status(self, text, state="idle"):
        fields = [self.core_status]
        if hasattr(self, "connection_status"):
            fields.append(self.connection_status)
        for field in fields:
            field.setText(text)
            field.setProperty("state", state)
            field.style().unpolish(field)
            field.style().polish(field)
            field.updateGeometry()
            field.update()

    def _mode_page(self):
        page, layout = page_layout(36, 24, "OnboardingPage")
        layout.addWidget(label("02  /  WALLET MODE", "SectionLabel"))
        layout.addWidget(label("Choose a wallet mode", "HeroTitle"))
        layout.addSpacing(12)
        choices = QHBoxLayout()
        choices.setSpacing(20)
        self.cold_choice = ChoiceRow(
            "cold", "Cold storage", "Private keys", accent="blue", card=True,
            tooltip="Create or recover an offline signing wallet. This mode holds private keys and signs transactions without connecting Core to peers.",
        )
        self.cold_choice.clicked.connect(lambda: self._select_mode("cold"))
        self.online_choice = ChoiceRow(
            "node", "Online node", "Watch only", accent="red", card=True,
            tooltip="Run a Bitcoin Core node and download the blockchain. Import your public wallet to view balances, activity and receiving addresses without private keys.",
        )
        self.online_choice.clicked.connect(lambda: self._select_mode("online"))
        choices.addWidget(self.cold_choice, 1)
        choices.addWidget(self.online_choice, 1)
        layout.addLayout(choices)
        layout.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        self.mode_continue = button("Continue  →", self._continue_mode, True)
        self.mode_continue.setEnabled(False)
        row.addWidget(self.mode_continue)
        layout.addLayout(row)
        self.tabs.addTab(page, "Mode")

    def _cold_network_page(self):
        page, layout = page_layout(30, 24, "OnboardingPage")
        layout.addWidget(label("Cold storage", "Eyebrow"))
        layout.addWidget(label(
            "Cold signer test mode" if self.dev_keep_network else "Permanently offline computer",
            "Title",
        ))
        notice = QFrame()
        notice.setObjectName("ColdNotice")
        notice_layout = QHBoxLayout(notice)
        notice_layout.setContentsMargins(16, 14, 16, 14)
        notice_layout.setSpacing(12)
        notice_icon = LineIcon("offline", "ColdNoticeIcon", stroke_width=1.8, inset=0)
        notice_icon.setFixedSize(22, 22)
        notice_layout.addWidget(notice_icon, 0, Qt.AlignmentFlag.AlignTop)
        notice_copy = QVBoxLayout()
        notice_copy.setSpacing(5)
        notice_copy.addWidget(label(
            "Computer networking stays on" if self.dev_keep_network else "Never take this computer back online",
            "NoticeTitle",
        ))
        if self.dev_keep_network:
            detail = "Bitcoin Core peer networking remains off. Swap is still disabled. Use test wallets only."
        else:
            detail = ("This permanently changes system networking. Once used for a real wallet, never take this computer back online. "
                      "Closing Core Companion or restarting Linux will not re-enable networking. "
                      "For the strongest safeguard, physically remove Wi-Fi, Ethernet, Bluetooth and other networking hardware.")
        warning = label(detail, "Muted")
        warning.setWordWrap(True)
        notice_copy.addWidget(warning)
        notice_layout.addLayout(notice_copy, 1)
        layout.addWidget(notice)
        self.permanent_acknowledgement = QCheckBox(
            "I understand: a real-wallet computer must never go back online."
            if not self.dev_keep_network else "Testing only: never put real wallet keys on this VM.")
        self.permanent_acknowledgement.setStyleSheet("QCheckBox::indicator { width: 22px; height: 22px; }")
        layout.addWidget(self.permanent_acknowledgement)
        memory_note = label("Swap is disabled while signing. Close other programs first; low memory can freeze the desktop.", "Muted")
        memory_note.setWordWrap(True)
        layout.addWidget(memory_note)
        layout.addStretch(1)
        footer = QHBoxLayout()
        footer.addStretch()
        continue_button = button("Continue (testing)" if self.dev_keep_network else "Commit to permanent offline mode",
                                 self._begin_cold_signer, True)
        continue_button.setEnabled(False)
        self.permanent_acknowledgement.toggled.connect(continue_button.setEnabled)
        continue_button.setObjectName("ColdContinue")
        footer.addWidget(continue_button)
        layout.addLayout(footer)
        self.tabs.addTab(page, "Cold storage")

    def _back_from_cold_notice(self):
        self.tabs.setCurrentIndex(self.cold_notice_previous)

    def _online_home(self):
        page, layout = page_layout(18, 16, "OnlinePage")
        layout.setSpacing(12)
        title_row = QHBoxLayout()
        title_copy = QVBoxLayout()
        title_copy.setSpacing(6)
        self.online_name = label("Your online node", "Title")
        self.online_name.setWordWrap(True)
        title_copy.addWidget(self.online_name)
        title_row.addLayout(title_copy, 1)
        title_row.addStretch()
        self.wallet_picker = ComboBox()
        self.wallet_picker.setMinimumWidth(210)
        self.wallet_picker.currentTextChanged.connect(self.select_wallet)
        title_row.addWidget(self.wallet_picker)
        title_row.addWidget(button("Import wallet", self._import_wallet_dialog))
        layout.addLayout(title_row)
        sync_card = QFrame()
        sync_card.setObjectName("SubtlePanel")
        sync_layout = QVBoxLayout(sync_card)
        sync_layout.setContentsMargins(18, 14, 18, 14)
        sync_layout.setSpacing(10)
        sync_row = QHBoxLayout()
        self.sync_label = label("Blockchain sync · not connected", "ActionTitle")
        sync_row.addWidget(self.sync_label)
        sync_row.addStretch()
        self.sync_detail = label("Local Bitcoin Core", "Muted")
        sync_row.addWidget(self.sync_detail)
        sync_layout.addLayout(sync_row)
        self.sync_progress = QProgressBar()
        self.sync_progress.setRange(0, 1000)
        self.sync_progress.setValue(0)
        self.sync_progress.setTextVisible(False)
        self.sync_progress.setFixedHeight(5)
        sync_layout.addWidget(self.sync_progress)
        layout.addWidget(sync_card)
        self.wallet_empty = QFrame()
        self.wallet_empty.setObjectName("Surface")
        self.wallet_empty.setMinimumHeight(280)
        empty = QHBoxLayout(self.wallet_empty)
        empty.setContentsMargins(32, 30, 32, 30)
        empty.setSpacing(32)
        empty.addStretch(1)
        empty_art = ScanIllustration()
        empty_art.setFixedSize(172, 172)
        empty.addWidget(empty_art)
        empty_copy = QVBoxLayout()
        empty_copy.setSpacing(14)
        empty_copy.addStretch()
        empty_copy.addWidget(label("YOUR PUBLIC WALLET", "SectionLabel"))
        empty_copy.addWidget(label("Import your wallet", "Title"))
        empty_detail = label("Scan the public wallet from your cold signer.", "PageDescription")
        empty_detail.setWordWrap(True)
        empty_copy.addWidget(empty_detail)
        empty_copy.addWidget(button("Import wallet", self._import_wallet_dialog, True), 0, Qt.AlignmentFlag.AlignLeft)
        empty_note = label("Public keys only. Your private keys stay on the signer.", "FooterNote")
        empty_note.setWordWrap(True)
        empty_copy.addWidget(empty_note)
        empty_copy.addStretch()
        empty.addLayout(empty_copy, 3)
        empty.addStretch(1)
        layout.addWidget(self.wallet_empty, 1)
        self.wallet_content = QWidget()
        wallet_layout = QVBoxLayout(self.wallet_content)
        wallet_layout.setContentsMargins(0, 0, 0, 0)
        wallet_layout.setSpacing(14)
        layout.addWidget(self.wallet_content, 1)
        layout = wallet_layout
        self.wallet_content.hide()
        self.wallet_picker.hide()
        balances = QFrame()
        balances.setObjectName("BalanceHero")
        balances.setMinimumHeight(120)
        kpis = QHBoxLayout(balances)
        kpis.setContentsMargins(10, 6, 10, 6)
        kpis.setSpacing(18)
        self.balance = self._kpi(kpis, "AVAILABLE BALANCE · BTC", "—", main=True)
        self.pending = self._kpi(kpis, "UNCONFIRMED · BTC", "—")
        self.immature = self._kpi(kpis, "MINED REWARDS · LOCKED", "—")
        self.immature.setToolTip("Newly mined block rewards cannot be spent until they mature after 100 blocks.")
        self.immature.parentWidget().hide()
        layout.addWidget(balances)
        actions = QGridLayout()
        actions.setHorizontalSpacing(14)
        actions.setVerticalSpacing(12)
        receive_action = ActionRow(
            "↓", "Receive", "", primary=True,
            tooltip="Create an address and QR code using Bitcoin Core.",
        )
        receive_action.clicked.connect(self._open_receive)
        send_action = ActionRow(
            "⇧", "Send", "",
            tooltip="Create an unsigned PSBT for your cold signer.", icon_key="send",
        )
        send_action.clicked.connect(lambda: self.tabs.setCurrentIndex(8))
        addresses_action = ActionRow(
            "▣", "Addresses", "",
            tooltip="Browse addresses known to the selected Core wallet.",
        )
        addresses_action.clicked.connect(lambda: self.tabs.setCurrentIndex(5))
        tools_action = ActionRow(
            "⚙", "Tools", "",
            tooltip="Import a signed PSBT, scan its QR, or change appearance.",
        )
        tools_action.clicked.connect(lambda: self.tabs.setCurrentIndex(6))
        for index, action in enumerate((receive_action, send_action, addresses_action, tools_action)):
            action.setMinimumHeight(82)
            actions.addWidget(action, 0, index)
        layout.addLayout(actions)
        activity_card = QFrame()
        activity_card.setObjectName("Surface")
        activity = QVBoxLayout(activity_card)
        activity.setContentsMargins(18, 16, 18, 18)
        activity.setSpacing(12)
        activity_header = QHBoxLayout()
        activity_header.addWidget(label("Recent activity", "Heading"))
        activity_header.addStretch()
        all_activity = button("All  →", lambda: self.tabs.setCurrentIndex(3))
        all_activity.setObjectName("Quiet")
        activity_header.addWidget(all_activity)
        activity.addLayout(activity_header)
        self.recent = self.table(["DATE", "LABEL", "AMOUNT · BTC"])
        self.recent.setObjectName("EmbeddedTable")
        self.recent.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.recent.setMinimumHeight(150)
        self.recent.cellActivated.connect(self.transaction_details)
        activity.addWidget(self.recent, 1)
        layout.addWidget(activity_card, 1)
        viewport = QScrollArea()
        viewport.setWidgetResizable(True)
        viewport.setFrameShape(QFrame.Shape.NoFrame)
        viewport.setWidget(page)
        self.tabs.addTab(viewport, "Wallet")

    def _kpi(self, parent_layout, heading, value, *, main=False):
        card = QFrame()
        card.setObjectName("PageContent")
        column = QVBoxLayout(card)
        column.setContentsMargins(18, 18, 18, 18)
        column.setSpacing(10)
        column.addWidget(label(heading, "SectionLabel"))
        result = label(value, "DashboardAmount" if main else "KPIValue")
        column.addWidget(result)
        parent_layout.addWidget(card, 2 if main else 1)
        return result

    def _select_mode(self, mode):
        if mode == "online" and not self._allow_online():
            return
        self.mode_choice = mode
        self.cold_choice.setChecked(mode == "cold")
        self.online_choice.setChecked(mode == "online")
        self.mode_continue.setObjectName("ColdContinue" if mode == "cold" else "OnlineContinue")
        self.mode_continue.style().unpolish(self.mode_continue)
        self.mode_continue.style().polish(self.mode_continue)
        self.mode_continue.setEnabled(True)

    def _continue_mode(self):
        if self.mode_choice == "online" and not self._allow_online():
            return
        if self.mode_choice == "cold":
            self.start_cold_signer()
        elif self.mode_choice == "online":
            if self.service:
                self.sync_timer.start()
                self.tabs.setCurrentIndex(2)
            else:
                self.connection_purpose = "online"
                cookie = default_cookie_path()
                if cookie.is_file():
                    self._use_core_connection(cookie, 8332)
                    self.connect()
                else:
                    self._start_managed_node()

    def _toggle_help_mode(self):
        self.help_mode = not self.help_mode
        controls = [self.help_button] + [control for control in self.findChildren(IconButton)
                                       if control.property("helpToggle")]
        for control in controls:
            control.set_caption("Help on" if self.help_mode else "Help")
            control.setProperty("active", self.help_mode)
            control.style().unpolish(control)
            control.style().polish(control)

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.setStyleSheet(stylesheet(self.dark_mode))
        self.theme_button.set_caption("Light mode" if self.dark_mode else "Dark mode")
        self.theme_button.set_glyph("light" if self.dark_mode else "dark")
        self._style_transaction_values()

    def _style_transaction_values(self):
        positive = QColor("#93e2c1" if self.dark_mode else "#176548")
        pending = QColor("#efc57d" if self.dark_mode else "#86580f")
        negative = QColor("#f8a69a" if self.dark_mode else "#a13b34")
        for row, tx in enumerate(self.rows):
            status = self.transactions.item(row, 0)
            if status:
                confirmations = tx.get("confirmations", 0)
                status.setForeground(negative if confirmations < 0 else pending if confirmations == 0 else positive)
            amount = self.transactions.item(row, 3)
            if amount and tx.get("amount", 0) > 0:
                amount.setForeground(positive)

    def _install_help_targets(self):
        descriptions = {
            "Connect to Bitcoin Core": "Connect to the local node using its private cookie. Credentials stay on this computer.",
            "Download & verify Bitcoin Core": "Download Core from its official hosts. Install only after its archive hash and three pinned release signatures pass verification.",
            "Cancel": "Stop the download. An existing Core installation is preserved.",
            "Advanced connection settings…": "Change the local RPC port if automatic connection does not work.",
            "Choose wallet mode  →": "Choose an offline signer with private keys or an online watch-only node.",
            "Continue  →": "Continue with the selected wallet mode.",
            "Continue": "Turn off system swap and, in normal mode, networking before opening the cold signer.",
            "Import wallet": "Import public receive and change descriptors from your cold signer. Core creates a watch-only wallet and scans available blocks.",
            "All  →": "Show the selected wallet’s transaction history.",
            "↻  Refresh": "Read the selected wallet’s latest balances, transactions and addresses from Core.",
            "‹  Newer": "Show the previous page of up to 100 transaction entries.",
            "Older  ›": "Show the next page of up to 100 older transaction entries.",
            "Generate address": "Ask Core for a fresh receiving address with your optional label.",
            "New address": "Open the receiving form to generate a fresh address.",
            "Copy address": "Copy this public address. Compare the complete pasted address with your cold signer before use.",
            "Done": "Save the address label and return to the wallet.",
            "Disconnect": "Disconnect this interface. The Core node keeps running.",
            "Connect": "Connect to Core on this computer using the selected RPC port.",
            "Close": "Close this information window.",
        }
        fields = {
            self.wallet_picker: "Select a loaded Core wallet with private keys disabled.",
            self.search: "Filter transaction entries on this page by label, address or transaction ID.",
            self.receive_label: "An optional description stored with the new receiving address in Core.",
            self.address: "The complete public receiving address generated by Core.",
            self.port: "The local Core RPC port. The connection always uses 127.0.0.1.",
            self.transactions: "Transactions reported by Core for this wallet. Double-click a row to read its details.",
            self.recent: "Recent wallet entries reported by Core. Double-click a row to read its details.",
            self.addresses: "Receiving addresses and labels stored by Core. Double-click a row for details. Received totals are not spendable balances.",
            self.sync_progress: "The portion of blockchain history verified by Bitcoin Core. Wallet balances may be incomplete until synchronization finishes.",
        }
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QPushButton, QLineEdit, QComboBox, QPlainTextEdit, QTableWidget, QProgressBar, ActionRow)):
                if isinstance(widget, QPushButton):
                    text = widget.text()
                elif hasattr(widget, "placeholderText"):
                    text = widget.placeholderText()
                else:
                    text = ""
                if not widget.toolTip():
                    widget.setToolTip(fields.get(widget) or descriptions.get(text)
                                      or ("Return to the previous screen." if "Back" in text else "View this wallet action."))
                widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Enter and self.help_mode and watched.toolTip():
            QToolTip.showText(watched.mapToGlobal(watched.rect().bottomLeft()), watched.toolTip(), watched)
        elif event.type() == QEvent.Type.Leave and self.help_mode:
            QToolTip.hideText()
        return super().eventFilter(watched, event)

    def page(self, title, *, scroll=False):
        widget, layout = page_layout(22, 16, "OnlinePage")
        if scroll:
            viewport = QScrollArea()
            viewport.setWidgetResizable(True)
            viewport.setFrameShape(QFrame.Shape.NoFrame)
            viewport.setWidget(widget)
            self.tabs.addTab(viewport, title)
        else:
            self.tabs.addTab(widget, title)
        return layout

    def _wallet_page_heading(self, layout, title, description=""):
        layout.addWidget(label(title, "Title"))
        if description:
            detail = label(description, "PageDescription")
            detail.setWordWrap(True)
            layout.addWidget(detail)

    def _dialog(self, title, description="", *, size=(800, 540), online=False):
        dialog = QDialog(self)
        dialog.setObjectName("OnlineDialog" if online else "CompanionDialog")
        dialog.setWindowTitle(f"{title} · Core Companion")
        dialog.resize(*size)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)
        heading = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(8)
        copy.addWidget(label(title, "CompactTitle"))
        if description:
            detail = label(description, "FormHint")
            detail.setWordWrap(True)
            copy.addWidget(detail)
        heading.addLayout(copy, 1)
        help_button = IconButton("help", "Help on" if self.help_mode else "Help", self._toggle_help_mode,
                                 tooltip="Turn on instant explanations when hovering over a control.")
        help_button.setProperty("helpToggle", True)
        help_button.setProperty("active", self.help_mode)
        help_button.installEventFilter(self)
        heading.addWidget(help_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)
        return dialog, layout

    def _dialog_help(self, dialog):
        descriptions = {
            "Close": "Close this window.",
            "Back": "Close this form without applying changes.",
            "Connect": "Connect to Bitcoin Core on this computer using the selected port.",
            "Disconnect": "Disconnect this interface. The Bitcoin Core node keeps running.",
            "Core details": "Show the complete response supplied by Bitcoin Core.",
        }
        for control in dialog.findChildren(QWidget):
            if isinstance(control, (QPushButton, QLineEdit, QPlainTextEdit, QComboBox)):
                if not control.toolTip():
                    control.setToolTip(descriptions.get(control.text(), "Activate this control.")
                                       if isinstance(control, QPushButton) else "Complete information supplied by Bitcoin Core.")
                control.installEventFilter(self)

    def table(self, headers):
        is_addresses = "ADDRESS" in headers
        table = EmptyTable(0, len(headers), empty_title="No saved addresses" if is_addresses else "No activity yet",
                           empty_hint="Generate an address to see it here." if is_addresses else "Wallet transactions will appear here.")
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(48)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)
        return table

    def _history(self):
        page = self.page("History")
        self._wallet_page_heading(page, "Wallet activity")
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search this page…")
        self.search.setMaximumWidth(340)
        self.search.textChanged.connect(self.filter_history)
        bar.addWidget(self.search)
        bar.addStretch()
        bar.addWidget(button("↻  Refresh", self.refresh))
        page.addLayout(bar)
        self.transactions = self.table(["STATUS", "DATE", "DESCRIPTION", "AMOUNT · BTC"])
        self.transactions.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col, width in [(0, 155), (1, 175), (3, 180)]:
            self.transactions.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.transactions.setColumnWidth(col, width)
        self.transactions.cellActivated.connect(self.transaction_details)
        page.addWidget(self.transactions, 1)
        bar = QHBoxLayout()
        self.page_label = label("No activity loaded", "Muted")
        bar.addWidget(self.page_label)
        bar.addStretch()
        bar.addWidget(button("‹  Newer", lambda: self.paginate(-100)))
        bar.addWidget(button("Older  ›", lambda: self.paginate(100)))
        page.addLayout(bar)
        page.addWidget(label("Double-click an entry for details.", "FooterNote"))

    def _receive(self):
        page = self.page("Receive", scroll=True)
        self._wallet_page_heading(page, "Receive Bitcoin")
        card = QFrame()
        card.setObjectName("FormPanel")
        card.setMinimumHeight(378)
        form = QVBoxLayout(card)
        form.setContentsMargins(28, 28, 28, 28)
        form.setSpacing(20)
        receive_content = QHBoxLayout()
        receive_content.setSpacing(32)
        self.receive_visual = QStackedWidget()
        self.receive_visual.setFixedSize(320, 320)
        empty = QFrame()
        empty.setObjectName("SubtlePanel")
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.setSpacing(14)
        empty_layout.addStretch()
        icon = LineIcon("receive", "BlueIcon", stroke_width=1.7, inset=14)
        icon.setFixedSize(64, 64)
        empty_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_title = label("A new address", "EmptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_hint = label("Generate an address to show its QR code.", "EmptyHint")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint.setWordWrap(True)
        empty_layout.addWidget(empty_hint)
        empty_layout.addStretch()
        self.receive_visual.addWidget(empty)
        self.receive_qr = QLabel()
        self.receive_qr.setObjectName("QR")
        self.receive_qr.setFixedSize(320, 320)
        self.receive_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.receive_visual.addWidget(self.receive_qr)
        receive_content.addWidget(self.receive_visual, 0, Qt.AlignmentFlag.AlignTop)
        address_column = QVBoxLayout()
        address_column.setSpacing(12)
        address_column.addWidget(label("Label · optional", "FieldLabel"))
        self.receive_label = QLineEdit()
        self.receive_label.setPlaceholderText("e.g. Savings")
        address_column.addWidget(self.receive_label)
        row = QHBoxLayout()
        self.generate_button = button("Generate address", self.generate, True)
        row.addWidget(self.generate_button)
        row.addStretch()
        address_column.addLayout(row)
        self.receive_details = QWidget()
        details = QVBoxLayout(self.receive_details)
        details.setContentsMargins(0, 12, 0, 0)
        details.setSpacing(12)
        self.receive_used = label("Address ready", "InlineNotice")
        self.receive_used.setProperty("tone", "success")
        details.addWidget(self.receive_used)
        self.receive_mark_used = QCheckBox("Mark as used")
        self.receive_mark_used.setStyleSheet("QCheckBox::indicator { width: 22px; height: 22px; }")
        details.addWidget(self.receive_mark_used)
        details.addWidget(label("Receiving address", "FieldLabel"))
        self.address = QLineEdit()
        self.address.setReadOnly(True)
        self.address.setPlaceholderText("Your receiving address will appear here")
        self.address.setFont(fixed_font(11))
        details.addWidget(self.address)
        row = QHBoxLayout()
        row.addWidget(IconButton("copy", "Copy address", self.copy_address,
                                 tooltip="Copy the complete receiving address. Verify the pasted address on your cold signer."))
        row.addStretch()
        details.addLayout(row)
        self.receive_details.hide()
        address_column.addWidget(self.receive_details)
        address_column.addStretch()
        receive_content.addLayout(address_column, 1)
        form.addLayout(receive_content)
        page.addWidget(card)
        note = label("Verify this address on your cold signer before receiving Bitcoin.", "InfoStrip")
        note.setMinimumHeight(58)
        note.setStyleSheet("font-size: 16px; font-weight: 600; padding: 16px;")
        note.setWordWrap(True)
        page.addWidget(note)
        page.addStretch()
        footer = QHBoxLayout()
        footer.addStretch()
        self.receive_done = button("Done", self._finish_receive, True)
        self.receive_done.hide()
        footer.addWidget(self.receive_done)
        page.addLayout(footer)

    def _addresses(self):
        page = self.page("Addresses")
        self._wallet_page_heading(page, "Addresses & labels")
        row = QHBoxLayout()
        row.addWidget(label("RECEIVING ADDRESSES", "SectionLabel"))
        row.addStretch()
        row.addWidget(button("New address", self._open_receive, True))
        page.addLayout(row)
        self.addresses = self.table(["LABEL", "ADDRESS", "USED"])
        self.addresses.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in [(0, 170), (2, 175)]:
            self.addresses.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.addresses.setColumnWidth(column, width)
        self.addresses.cellActivated.connect(self.address_details)
        page.addWidget(self.addresses, 1)
        page.addWidget(label("Received amounts are lifetime totals. Change addresses are omitted.", "FooterNote"))

    def _tools(self):
        page = self.page("Tools")
        self._wallet_page_heading(page, "Tools & Settings")
        self.cold_button = self.mode_continue
        imported = ActionRow("import", "Import PSBT", "Scan a QR, paste, or load a PSBT file.",
                             tooltip="Import a signed transaction and review it before broadcasting.", icon_key="import")
        imported.clicked.connect(self._import_psbt_dialog)
        page.addWidget(imported)
        privacy = ActionRow("shield-check", "Network privacy", "Tor-only downloads and node connections.",
                            tooltip="Change Tor-only mode. Disabling it exposes your public IP to services and peers.", icon_key="shield-check")
        privacy.clicked.connect(self._privacy_dialog)
        page.addWidget(privacy)
        appearance = ActionRow("dark", "Change appearance", "", tooltip="Switch light and dark mode.", icon_key="dark")
        appearance.clicked.connect(self._toggle_theme)
        page.addWidget(appearance)
        page.addStretch()

    def _connection_dialog(self):
        self.connection, layout = self._dialog("Local connection", "Bitcoin Core on this computer.", size=(620, 410))
        panel = QFrame()
        panel.setObjectName("FormPanel")
        content = QVBoxLayout(panel)
        content.setContentsMargins(22, 20, 22, 20)
        content.setSpacing(16)
        self.connection_status = label(self.core_status.text(), "CoreStatus")
        self.connection_status.setWordWrap(True)
        content.addWidget(self.connection_status)
        self.connection_binary = label("", "FormHint")
        self.connection_binary.setWordWrap(True)
        content.addWidget(self.connection_binary)
        self.connection_version = label("", "FormHint")
        content.addWidget(self.connection_version)
        form = QFormLayout()
        form.setSpacing(12)
        self.port = QLineEdit("8332")
        self.port.setReadOnly(self.tor_enabled)
        self.port.setToolTip("The local Bitcoin Core RPC port. Connections always use 127.0.0.1.")
        form.addRow("Core port", self.port)
        content.addLayout(form)
        note = label(
            "Local authentication is automatic. Change the port only if Core uses a different one.", "FormHint",
        )
        note.setWordWrap(True)
        content.addWidget(note)
        layout.addWidget(panel)
        layout.addStretch()
        row = QHBoxLayout()
        row.addWidget(button("Disconnect", self.disconnect))
        row.addStretch()
        row.addWidget(button("Close", self.connection.hide))
        row.addWidget(button("Connect", self.connect, True))
        layout.addLayout(row)
        self._dialog_help(self.connection)

    def show_connection(self):
        if not self._allow_online():
            return
        if self.tabs.currentIndex() not in (0, 1):
            self.connection_purpose = "online"
        managed = self.managed_core_process
        binary = managed.program() if managed is not None else ""
        self.connection_binary.setText("Executable: " + binary if binary else "Executable: external Core (path is not reported by RPC)")
        self.connection_version.setText("Core version: " + str(getattr(self, "node_info", {}).get("subversion", "Not connected")))
        self.connection.show()
        self.connection.raise_()
        self.connection.activateWindow()

    def _installed_core_binary(self):
        root = companion_data_dir() / "bitcoin-core"
        binaries = [path for path in root.glob("*/bin/bitcoind")
                    if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", path.parent.parent.name)
                    and path.is_file() and not path.is_symlink() and os.access(path, os.X_OK)]
        return max(binaries, key=lambda path: tuple(map(int, path.parent.parent.name.split(".")))) if binaries else None

    def _import_wallet_dialog(self):
        if self.service is None:
            self.statusBar().showMessage("Connect to your online node first.")
            return
        dialog, layout = self._dialog("Import your wallet", "Scan the public wallet exported by your cold signer.", size=(800, 560), online=True)
        panel = QFrame()
        panel.setObjectName("FormPanel")
        fields = QVBoxLayout(panel)
        fields.setContentsMargins(22, 20, 22, 20)
        fields.setSpacing(14)
        fields.addWidget(label("Wallet name", "FieldLabel"))
        name = QLineEdit()
        name.setPlaceholderText("Wallet name")
        name.setToolTip("A name for the new watch-only wallet stored by Core on this computer.")
        name.installEventFilter(self)
        fields.addWidget(name)
        fields.addWidget(label("Public wallet", "FieldLabel"))
        payload = QPlainTextEdit()
        payload.setPlaceholderText("Scan or paste a descriptor, xpub or zpub")
        payload.setFont(fixed_font(10))
        payload.setToolTip("Import a public descriptor, account xpub or zpub. Bare xpubs use native SegWit; use a descriptor for another address type or hardware signing origin. Never paste recovery words or private keys.")
        payload.installEventFilter(self)
        fields.addWidget(payload, 1)
        scanner = QRScanner(dialog)
        scan = button("Scan QR", scanner.scan)
        scan.setToolTip("Open the camera to scan the public wallet exported by your cold signer.")
        scan.installEventFilter(self)
        fields.addWidget(scan, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(panel, 1)

        def read_scan(text):
            payload.setPlainText(text)
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    name.setText(str(data.get("name", "")))
            except ValueError:
                pass

        scanner.decoded.connect(read_scan)
        scanner.failed.connect(lambda message: QMessageBox.warning(dialog, "QR scanner", message))

        def do_import():
            text = payload.toPlainText().strip()
            if not text or len(text) > 65536:
                QMessageBox.warning(dialog, "Wallet data", "Scan or paste the public wallet descriptors.")
                return
            try:
                data = json.loads(text) if text.startswith("{") else {"descriptors": text.splitlines()}
                if not isinstance(data, dict):
                    raise ValueError()
                descriptors = data.get("descriptors")
            except ValueError:
                QMessageBox.warning(dialog, "Wallet data", "The wallet QR could not be read.")
                return
            wallet_name = name.text().strip() or str(data.get("name", "")).strip()
            service = self.service
            self.connection_purpose = "online"
            scanner.stop()
            dialog.accept()
            self.task("Importing wallet and scanning blockchain history…",
                      lambda: service.import_public_wallet(wallet_name, descriptors),
                      lambda result: self.connected(service, result, wallet_name))

        footer = QHBoxLayout()
        back = button("Back", dialog.reject)
        back.setToolTip("Close this form without importing a wallet.")
        back.installEventFilter(self)
        footer.addWidget(back)
        footer.addStretch()
        proceed = button("Import wallet", do_import, True)
        proceed.setToolTip("Validate the public descriptors, create the watch-only wallet and scan available history. A pruned node cannot scan discarded blocks.")
        proceed.installEventFilter(self)
        footer.addWidget(proceed)
        layout.addLayout(footer)
        self._dialog_help(dialog)
        dialog.exec()
        scanner.stop()

    def download_bitcoin_core(self):
        if not self._allow_online():
            return
        if sys.platform != "linux":
            QMessageBox.information(
                self,
                "Bitcoin Core download",
                "Automatic Bitcoin Core download and verification is currently available on Linux only.",
            )
            return
        if self.cold_session:
            self.statusBar().showMessage("Close the cold signer before downloading Bitcoin Core.")
            return
        if self.core_download_process is not None:
            return
        if not self._ensure_tor(self.download_bitcoin_core):
            return
        missing = [tool for tool in ("gpg", "curl") if not _system_tool(tool)]
        if missing:
            QMessageBox.warning(
                self,
                "Verification tools required",
                "Install the verification tools with `sudo apt install gnupg curl`, then try again.",
            )
            return
        self.core_download_stderr = ""
        self.core_download_cancelled = False
        self.download_button.setEnabled(False)
        self.download_progress.show()
        self.cancel_download_button.show()
        self._set_core_status("Downloading and verifying Bitcoin Core…")
        process = QProcess(self)
        self.core_download_process = process
        process.readyReadStandardError.connect(lambda p=process: self._read_core_download_error(p))
        process.finished.connect(
            lambda code, status, p=process: self._core_download_finished(p, code, status)
        )
        process.errorOccurred.connect(lambda error, p=process: self._core_download_error(p, error))
        arguments = ["-E", "-s", "-B", str(Path(__file__).with_name("core_download.py"))]
        if self.tor_enabled:
            arguments += ["--tor-proxy", self.tor.proxy]
        process.start(sys.executable, arguments)

    def _read_core_download_error(self, process):
        self.core_download_stderr = (self.core_download_stderr + bytes(process.readAllStandardError()).decode("utf-8", "replace"))[-6000:]

    def _finish_core_download_ui(self, process):
        self._read_core_download_error(process)
        if self.core_download_process is process:
            self.core_download_process = None
        self.download_progress.hide()
        self.cancel_download_button.hide()
        self.cancel_download_button.setEnabled(True)
        self.download_button.setEnabled(True)

    def _core_download_finished(self, process, exit_code, exit_status):
        if self.core_download_process is not process:
            return
        output = bytes(process.readAllStandardOutput()).decode("utf-8", "replace").strip()
        self._finish_core_download_ui(process)
        if self.core_download_closing:
            QTimer.singleShot(0, self.close)
            return
        if self.core_download_cancelled:
            self.core_download_cancelled = False
            self._set_core_status("Bitcoin Core download cancelled")
            self.statusBar().showMessage("Bitcoin Core download cancelled")
            return
        try:
            result = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            result = {"ok": False, "error": "The download helper returned no valid result."}
        if exit_status != QProcess.ExitStatus.NormalExit or exit_code != 0 or not result.get("ok"):
            self._set_core_status("Bitcoin Core download was not verified", "error")
            detail = result.get("error", "The verification process stopped.")
            logs = self.core_download_stderr.strip()
            if logs:
                detail += "\n\n" + logs[-3000:]
            QMessageBox.critical(self, "Bitcoin Core was not installed", detail)
            return
        self.downloaded_bitcoind = result["path"]
        self._set_core_status(f"Bitcoin Core {result['version']} verified and installed")
        if self.mode_choice == "online":
            self._start_managed_node(result["path"])
        else:
            self.statusBar().showMessage("Core is ready. Choose Online Node to start syncing and connect.")

    def _use_core_connection(self, cookie_path, port):
        self.core_cookie_path = Path(cookie_path)
        self.port.setText(str(port))

    def _start_managed_node(self, binary=None, *, prefer_existing=True):
        if not self._allow_online():
            return
        if sys.platform != "linux":
            self.statusBar().showMessage("Starting a downloaded Core node is available on Linux.")
            return
        default_cookie = default_cookie_path()
        if not self.tor_enabled and prefer_existing and default_cookie.is_file():
            self._use_core_connection(default_cookie, 8332)
            self.connect()
            return

        binary = Path(binary) if binary else self._installed_core_binary()
        if not binary or not binary.is_file():
            self._set_core_status("Install verified Core from offline media" if self.cold_required else "Download and verify Bitcoin Core first", "error")
            self.statusBar().showMessage("Download and verify Bitcoin Core from Welcome, then choose Online Node.")
            return

        if not self._ensure_tor(lambda: self._start_managed_node(binary, prefer_existing=prefer_existing)):
            return
        data_dir = managed_node_dir()
        cookie = data_dir / ".cookie"
        if self.managed_core_process is not None and self.managed_core_process.poll() is None:
            self._use_core_connection(cookie, self.managed_rpc_port)
            self.connect()
            return
        if self.tor_enabled:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                self.managed_rpc_port = listener.getsockname()[1]
        else:
            self.managed_rpc_port = MANAGED_RPC_PORT
        self._use_core_connection(cookie, self.managed_rpc_port)
        if not self.tor_enabled and prefer_existing and cookie.is_file():
            self._set_core_status("Connecting to your Bitcoin Core node…")
            self.connect()
            return

        try:
            data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            data_dir.chmod(0o700)
            arguments = [
                f"-datadir={data_dir}",
                "-conf=/dev/null",
                "-chain=main",
                "-rpcbind=127.0.0.1",
                "-rpcallowip=127.0.0.1",
                "-daemon=0",
                "-server=1",
                f"-rpcport={self.managed_rpc_port}",
                f"-prune={PRUNE_TARGET_MIB}",
            ]
            if self.tor_enabled:
                arguments += core_tor_arguments(self.tor.proxy)
            self.managed_node_tor_proxy = self.tor.proxy if self.tor_enabled else None
            with (data_dir / "companion-startup.log").open("ab", buffering=0) as log_file:
                self.managed_core_process = subprocess.Popen(
                    [str(binary), *arguments],
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
        except (OSError, ValueError) as exc:
            self._set_core_status("Bitcoin Core could not start", "error")
            self.statusBar().showMessage(f"Could not start Bitcoin Core: {exc}")
            return

        self._set_core_status("Starting Bitcoin Core and connecting…")
        self.statusBar().showMessage("Bitcoin Core is starting. Initial blockchain sync will continue in the background.")
        self.node_start_deadline = time.monotonic() + 90
        self.node_start_timer.start()
        self._poll_managed_node()

    def _poll_managed_node(self):
        if time.monotonic() >= self.node_start_deadline:
            self.node_start_timer.stop()
            self._set_core_status("Core has not connected yet", "error")
            self.statusBar().showMessage("Core may still be starting. Try Connect again or review its startup log.")
            return
        if self.managed_core_process is not None and self.managed_core_process.poll() is not None:
            self.node_start_timer.stop()
            self.managed_core_process = None
            self._set_core_status("Bitcoin Core could not start", "error")
            self.statusBar().showMessage(
                f"Bitcoin Core stopped during startup. See {managed_node_dir() / 'companion-startup.log'} for details."
            )
            return
        if self.core_cookie_path and self.core_cookie_path.is_file() and not self.busy:
            self.connect()

    def _core_download_error(self, process, error):
        if process != self.core_download_process or error != QProcess.ProcessError.FailedToStart:
            return
        self._finish_core_download_ui(process)
        if self.core_download_closing:
            QTimer.singleShot(0, self.close)
            return
        if self.core_download_cancelled:
            self.core_download_cancelled = False
            self._set_core_status("Bitcoin Core download cancelled")
            self.statusBar().showMessage("Bitcoin Core download cancelled")
            return
        self._set_core_status("Bitcoin Core download could not start", "error")
        QMessageBox.critical(
            self,
            "Bitcoin Core download could not start",
            "The verification helper could not be started. Try launching Companion again.",
        )

    def cancel_core_download(self):
        process = self.core_download_process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            if not self.core_download_closing:
                self.core_download_cancelled = True
            self.cancel_download_button.setEnabled(False)
            self.statusBar().showMessage("Stopping the Core download and verification…")
            process.terminate()
            QTimer.singleShot(4000, lambda p=process: self._kill_core_download(p))

    def _kill_core_download(self, process):
        if process == self.core_download_process and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def start_cold_signer(self):
        if sys.platform != "linux":
            self.statusBar().showMessage("Cold signer setup currently requires Linux.")
            return
        if self.core_download_process is not None:
            self.statusBar().showMessage("Finish or cancel the Core download before starting cold storage.")
            return
        if not self._installed_core_binary():
            self._set_core_status("Install verified Core from offline media" if self.cold_required else "Download and verify Bitcoin Core first", "error")
            self.statusBar().showMessage("Never reconnect. Transfer a verified Core installation from trusted offline media." if self.cold_required else "Download and verify Core on Welcome before starting cold storage.")
            self.tabs.setCurrentIndex(0)
            return
        if self.busy:
            if self.service is None:
                self.pending_cold_start = True
                self.statusBar().showMessage("Preparing cold storage…")
                return
            self.statusBar().showMessage("Wait for the local Core connection check to finish, then continue to cold storage.")
            return
        if self.cold_process and self.cold_process.state() != QProcess.ProcessState.NotRunning:
            return
        self.cold_notice_previous = self.tabs.currentIndex()
        self.tabs.setCurrentIndex(7)

    def _begin_cold_signer(self):
        if sys.platform != "linux":
            self.statusBar().showMessage("Cold signer setup currently requires Linux.")
            return
        if self.core_download_process is not None:
            self.statusBar().showMessage("Finish or cancel the Core download before starting cold storage.")
            return
        if self.busy:
            self.statusBar().showMessage("Wait for the local Core connection check to finish, then continue to cold storage.")
            return
        if self.cold_process and self.cold_process.state() != QProcess.ProcessState.NotRunning:
            return
        if self.cold_session:
            self._restore_cold_system()
            if self.cold_session:
                return
        bitcoind = self._installed_core_binary()
        if not bitcoind:
            self._set_core_status("Install verified Core from offline media" if self.cold_required else "Download and verify Bitcoin Core first", "error")
            self.statusBar().showMessage("Never reconnect. Transfer a verified Core installation from trusted offline media." if self.cold_required else "Download and verify Core on Welcome before starting cold storage.")
            self.tabs.setCurrentIndex(0)
            return
        if not self.permanent_acknowledgement.isChecked():
            return
        if self.tor_install_process is not None:
            self.statusBar().showMessage("Wait for Tor installation to finish before cold setup.")
            return
        if not self._stop_managed_node():
            return
        self.tor_pending = None
        self.tor.stop()
        if not self.dev_keep_network:
            try:
                PermanentAirgap.activate()
            except (ColdSetupError, OSError) as exc:
                if PermanentAirgap.is_committed():
                    self._lock_cold_installation()
                QMessageBox.critical(self, "Permanent offline setup incomplete",
                    str(exc) + "\n\nNo signer was started. This app will not enable networking. Keep this computer offline and retry setup.")
                return
            self._lock_cold_installation()
        session = ColdSystemSession(disable_networking=not self.dev_keep_network)
        self.cold_session = session
        try:
            session.begin()
            session.assert_disabled()
        except ColdSetupError as exc:
            try:
                session.restore()
            except ColdSetupError as restore_error:
                self.cold_button.setEnabled(False)
                self.cold_button_top.setEnabled(False)
                self.statusBar().showMessage("Cold setup stopped · system settings need attention")
                QMessageBox.critical(
                    self,
                    "System settings need attention",
                    f"Cold signer could not start: {exc}\n\nRestoration also needs attention: {restore_error}",
                )
            else:
                self.cold_session = None
                QMessageBox.critical(self, "Cold signer could not start", str(exc))
            return
        self.network.setText("DEVELOPMENT · NOT AIR-GAPPED" if self.dev_keep_network else "● Permanent offline policy verified")
        self.cold_session_id = secrets.token_hex(16)
        self.isolation_timer.start()
        self.sync_timer.stop()
        self.node_start_timer.stop()
        self.cold_temp_path = Path("/dev/shm") / f"core-companion-cold-{self.cold_session_id}"
        self.cold_button.setEnabled(False)
        self.cold_button_top.setEnabled(False)
        self.statusBar().showMessage(
            "DEV MODE · host networking on · Core P2P off · swap off"
            if self.dev_keep_network else "Permanent offline policy verified · swap off"
        )
        process = QProcess(self)
        self.cold_process = process
        entry = Path(__file__).resolve().parent.parent / "run.py"
        process.setProgram(sys.executable)
        arguments = [
            "-E", "-s", "-B", str(entry), "--cold-helper", "--bitcoind", str(bitcoind.resolve()),
            "--session-id", self.cold_session_id,
        ]
        if self.dev_keep_network:
            arguments.append("--dev-keep-network")
        process.setArguments(arguments)
        process.started.connect(lambda: setattr(self, "cold_process_group", int(process.processId())))
        process.readyReadStandardOutput.connect(
            lambda: self.hide() if process.canReadLine() and bytes(process.readLine()).strip() == b"COLD_SIGNER_READY" else None
        )
        process.finished.connect(self._cold_helper_finished)
        process.errorOccurred.connect(self._cold_helper_error)
        process.start()

    def _check_cold_isolation(self):
        if not self.cold_session or self.cold_restoring:
            return
        try:
            self.cold_session.assert_disabled()
        except ColdSetupError as exc:
            self.isolation_timer.stop()
            self._restore_cold_system()
            self.show()
            QMessageBox.critical(
                self, "Cold session stopped",
                f"The offline checks failed: {exc}\n\n"
                + ("Cleanup needs attention. Keep this app open and close the signer before restoring settings."
                   if self.cold_session else "The signer has been stopped. Check this computer before starting another session."),
            )

    def _stop_cold_process_group(self):
        group = self.cold_process_group
        if not group:
            if self.cold_process and self.cold_process.state() != QProcess.ProcessState.NotRunning:
                self.cold_process.terminate()
                if not self.cold_process.waitForFinished(5000):
                    self.cold_process.kill()
                    return self.cold_process.waitForFinished(5000)
            return True
        try:
            os.killpg(group, signal.SIGTERM)
        except ProcessLookupError:
            # The helper may have started but not yet called setsid(). Stop it
            # by PID and wait; never restore the host while it can still start Core.
            if self.cold_process and self.cold_process.state() != QProcess.ProcessState.NotRunning:
                try:
                    os.kill(group, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                if not self.cold_process.waitForFinished(5000):
                    self.cold_process.kill()
                    if not self.cold_process.waitForFinished(5000):
                        return False
            self.cold_process_group = None
            return True
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.cold_process and self.cold_process.state() != QProcess.ProcessState.NotRunning:
                self.cold_process.waitForFinished(100)
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                self.cold_process_group = None
                return True
            time.sleep(0.1)
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            self.cold_process_group = None
            return True
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.cold_process and self.cold_process.state() != QProcess.ProcessState.NotRunning:
                self.cold_process.waitForFinished(100)
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                self.cold_process_group = None
                return True
            time.sleep(0.1)
        return False

    def _restore_cold_system(self):
        if self.cold_restoring:
            return
        self.isolation_timer.stop()
        self.cold_restoring = True
        try:
            self._restore_cold_system_inner()
        finally:
            self.cold_restoring = False

    def _restore_cold_system_inner(self):
        isolation_state = (
            "Swap remains disabled; host networking was left on in development mode."
            if self.dev_keep_network else "Networking and swap remain disabled."
        )
        if not self._stop_cold_process_group():
            QMessageBox.critical(
                self,
                "Cold Core is still running",
                f"{isolation_state} The temporary Core process did not stop. "
                "Close it before restoring system settings.",
            )
            return
        if self.cold_temp_path:
            try:
                expected_name = f"core-companion-cold-{self.cold_session_id}"
                temp_root = Path("/dev/shm").resolve()
                if self.cold_temp_path.name != expected_name or self.cold_temp_path.parent.resolve() != temp_root:
                    raise ColdSetupError("The temporary cold-signer path failed its safety check.")
                if self.cold_temp_path.is_symlink():
                    raise ColdSetupError("The temporary cold-signer path is unexpectedly a symbolic link.")
                if self.cold_temp_path.exists():
                    from .linux_cold import _mount_type
                    if _mount_type(self.cold_temp_path) != "tmpfs":
                        raise ColdSetupError("The leftover cold-signer files are not on a RAM-backed filesystem.")
                    shutil.rmtree(self.cold_temp_path)
            except (OSError, ColdSetupError) as exc:
                QMessageBox.critical(
                    self,
                    "Temporary signer data remains",
                    f"{isolation_state} Temporary signer data could not be removed: {exc}",
                )
                return
        if self.cold_session:
            try:
                self.cold_session.restore()
            except ColdSetupError as exc:
                QMessageBox.critical(self, "System settings need attention", str(exc))
                self.statusBar().showMessage("Cold Core stopped · some system settings remain disabled")
                return
        self.cold_session = None
        self.cold_process = None
        self.cold_session_id = None
        self.cold_temp_path = None
        self.cold_button.setEnabled(True)
        self.cold_button_top.setEnabled(True)
        self.statusBar().showMessage(
            "Cold session closed · swap restored; networking was left on"
            if self.dev_keep_network else "Cold session closed · swap restored · networking remains permanently disabled"
        )
        if not self.dev_keep_network:
            try:
                PermanentAirgap.assert_enforced()
                self.network.setText("● Permanent offline policy verified")
            except ColdSetupError:
                self.network.setText("○ Offline protection NOT verified")
                self.statusBar().showMessage("Signer stopped · offline protection cannot be verified · keep this computer disconnected")

    def _cold_helper_finished(self, exit_code, exit_status):
        self._restore_cold_system()
        self.tabs.setCurrentIndex(1)
        self.show()
        self.raise_()

    def _cold_helper_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._restore_cold_system()
            QMessageBox.critical(self, "Cold signer could not open", "The cold signer helper process could not be started.")

    def _drain(self):
        try:
            done, result, error = self.events.get_nowait()
        except queue.Empty:
            return
        self.busy = False
        self.wallet_picker.setEnabled(True)
        if self.pending_cold_start:
            self.pending_cold_start = False
            self.connection_fallback = False
            self.service = None
            QTimer.singleShot(0, self.start_cold_signer)
            return
        if error:
            if self.connection_fallback:
                self.connection_fallback = False
                self.core_cookie_path = None
                if self.mode_choice != "online":
                    self._set_core_status("Bitcoin Core is ready. Choose a wallet mode.")
                    self.statusBar().showMessage("The previous node is not running. Online Node will start it when selected.")
                    return
                self.statusBar().showMessage("Starting the verified Bitcoin Core node…")
                QTimer.singleShot(0, lambda: self._start_managed_node(prefer_existing=False))
                return
            if self.node_start_timer.isActive():
                self._set_core_status("Starting Bitcoin Core…")
                self.statusBar().showMessage("Waiting for Core's local connection…")
                return
            if self.service is None:
                self._set_core_status("Could not connect. Check that Core is running.", "error")
            self.statusBar().showMessage(error)
        else:
            try:
                done(result)
            except Exception:
                self.statusBar().showMessage("Unexpected response data. Check Core compatibility.")

    def task(self, message, work, done, *, show_message=True):
        if self.busy:
            return
        self.busy = True
        self.wallet_picker.setEnabled(False)
        if show_message:
            self.statusBar().showMessage(message)
        def worker():
            try:
                result = work()
            except CoreError as exc:
                self.events.put((done, None, str(exc)))
            except Exception:
                self.events.put((done, None, "Operation failed. No automatic retry was attempted."))
            else:
                self.events.put((done, result, None))
        threading.Thread(target=worker, daemon=True).start()

    def _clear(self):
        self.wallet_content.hide()
        self.wallet_empty.show()
        self.wallet_picker.hide()
        self.wallet_picker.blockSignals(True)
        self.wallet_picker.clear()
        self.wallet_picker.blockSignals(False)
        for field in (self.balance, self.pending, self.immature):
            field.setText("—")
        self.online_name.setText("Connect to Bitcoin Core")
        self.sync_label.setText("Blockchain sync · not connected")
        self.sync_detail.setText("Local Bitcoin Core")
        self.sync_progress.setValue(0)
        self._set_core_status("Bitcoin Core not connected", "error")
        self._reset_receive()
        self.transactions.setRowCount(0)
        self.recent.setRowCount(0)
        self.addresses.setRowCount(0)
        self.rows = []
        self.skip = 0
        self.page_label.setText("No activity loaded")
        self.network.setText("○  Offline")

    def connect(self):
        if not self._allow_online():
            return
        if self.busy:
            return
        if not self._ensure_tor(self.connect):
            return
        if self.tor_enabled:
            if self.managed_core_process is None or self.managed_core_process.poll() is not None:
                self._start_managed_node(prefer_existing=False)
                return
            if self.managed_node_tor_proxy != self.tor.proxy:
                self._set_core_status("Restart the managed node to apply Tor-only mode", "error")
                return
            self._use_core_connection(managed_node_dir() / ".cookie", self.managed_rpc_port)
        try:
            cookie_path = self.core_cookie_path or default_cookie_path()
            if not cookie_path.is_file() and sys.platform == "linux" and self._installed_core_binary():
                self._start_managed_node(prefer_existing=False)
                return
            self.connection_fallback = (
                sys.platform == "linux"
                and not self.node_start_timer.isActive()
                and cookie_path in (default_cookie_path(), managed_node_dir() / ".cookie")
                and self._installed_core_binary() is not None
            )
            service = WalletService(CoreRPC(self.port.text(), cookie_path))
        except CoreError as exc:
            self.connection_fallback = False
            self._set_core_status("Could not connect. Check Core or review advanced settings.", "error")
            self.statusBar().showMessage(str(exc))
            return
        self.service = None
        self._clear()
        self._set_core_status("Connecting to Bitcoin Core…")
        self.task("Connecting to Core…", service.connect, lambda data: self.connected(service, data))

    def update_sync_status(self, chain):
        initial = bool(chain.get("initialblockdownload"))
        progress = 100.0 if not initial else float(chain.get("verificationprogress", 0)) * 100
        self.sync_progress.setValue(max(0, min(1000, round(progress * 10))))
        self.sync_label.setText(f"Blockchain sync · {progress:.1f}%" if initial else "Blockchain synced")
        storage = chain.get("size_on_disk")
        self.sync_detail.setText(
            f"{storage / (1024 ** 3):.1f} GB on disk"
            if isinstance(storage, (int, float)) else f"Block {chain.get('blocks', 0):,}"
        )
        if initial:
            self.statusBar().showMessage(
                f"Bitcoin Core is syncing · {progress:.1f}% verified · wallet data may be incomplete."
            )

    def refresh_sync_status(self):
        if not self.service or self.busy:
            return
        if self.wallet_picker.currentText():
            self.refresh()
            return
        service = self.service
        self.task(
            "Checking sync progress…",
            lambda: service.rpc.call("getblockchaininfo"),
            self.update_sync_status,
            show_message=False,
        )

    def connected(self, service, data, selected_wallet=None):
        if self.cold_required:
            self.service = None
            return
        if self.tor_enabled:
            try:
                assert_core_tor(data["node"], self.tor.proxy)
            except (ValueError, KeyError, TypeError) as exc:
                self._stop_managed_node()
                self._clear()
                self._set_core_status("Core did not confirm Tor-only protection", "error")
                self.statusBar().showMessage(str(exc))
                return
        self.connection_fallback = False
        self.node_start_timer.stop()
        if data["chain"].get("chain") != "main":
            self.service = None
            self._clear()
            self.statusBar().showMessage("This wallet view is set up for the expected Bitcoin chain only.")
            return
        self.connection.hide()
        self.service = service
        self.node_info = data["node"]
        self._set_core_status("Bitcoin Core connected", "connected")
        self.tabs.setCurrentIndex(2 if selected_wallet else (1 if self.connection_purpose == "welcome" else 2))
        self.update_sync_status(data["chain"])
        self.sync_timer.start()
        self.wallet_picker.blockSignals(True)
        self.wallet_picker.clear()
        self.wallet_picker.addItems(data["wallets"])
        if selected_wallet:
            self.wallet_picker.setCurrentText(selected_wallet)
        self.wallet_picker.blockSignals(False)
        self.wallet_content.setVisible(bool(data["wallets"]))
        self.wallet_empty.setVisible(not bool(data["wallets"]))
        self.wallet_picker.setVisible(bool(data["wallets"]))
        if data["wallets"]:
            self.refresh()
        else:
            self.online_name.setText("Your online node")
            self.statusBar().showMessage(
                "Import the public wallet QR from your cold signer."
            )

    def disconnect(self):
        if not self.busy:
            self.sync_timer.stop()
            self.service = None
            self._clear()
            self.setWindowTitle("Core Companion")
            self.connection.hide()
            self.statusBar().showMessage("Disconnected")

    def select_wallet(self, name):
        if not name or self.busy:
            return
        self.setWindowTitle(f"Core Companion — {name}")
        self._reset_receive()
        self.skip = 0
        self.transactions.setRowCount(0)
        self.recent.setRowCount(0)
        self.addresses.setRowCount(0)
        self.rows = []
        for field in (self.balance, self.pending, self.immature):
            field.setText("—")
        self.online_name.setText(f"{name} (watch-only)")
        self.sync_label.setText("Loading wallet activity…")
        self.refresh()

    def refresh(self):
        if self.busy or not self.service or not self.wallet_picker.currentText():
            return
        name, service, skip = self.wallet_picker.currentText(), self.service, self.skip
        self.task("Reading wallet from Core…", lambda: service.snapshot(name, skip), self.render)

    def render(self, data):
        groups = [data["balances"].get(key, {}) for key in ("mine", "watchonly")]
        total = lambda key: btc(sum((group.get(key, 0) for group in groups), 0))
        self.balance.setText(total("trusted"))
        self.pending.setText(total("untrusted_pending"))
        self.immature.setText(total("immature"))
        self.immature.parentWidget().setVisible(any(group.get("immature", 0) > 0 for group in groups))
        info, chain = data["info"], data["chain"]
        self.online_name.setText(f"{info['walletname']} (watch-only)")
        self.update_sync_status(chain)
        self.rows = list(reversed(data["transactions"]))
        self.transactions.setRowCount(len(self.rows))
        self.recent.setRowCount(min(4, len(self.rows)))
        for row, tx in enumerate(self.rows):
            confirmations = tx.get("confirmations", 0)
            status = "Conflicted" if confirmations < 0 else ("Abandoned" if tx.get("abandoned") else ("Unconfirmed" if confirmations == 0 else f"{confirmations} confirmed"))
            amount = tx.get("amount", 0)
            values = [status, datetime.fromtimestamp(tx.get("time", 0)).strftime("%d %b %Y · %H:%M"), tx.get("label") or tx.get("category", ""), ("+" if amount > 0 else "") + btc(amount)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(tx.get("txid", ""))
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(fixed_font(11))
                self.transactions.setItem(row, column, item)
            if row < 4:
                recent_values = [
                    datetime.fromtimestamp(tx.get("time", 0)).strftime("%d %b %Y"),
                    tx.get("label") or tx.get("category", ""),
                    ("+" if amount > 0 else "") + btc(amount),
                ]
                for column, value in enumerate(recent_values):
                    recent_item = QTableWidgetItem(value)
                    if column == 2:
                        recent_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        recent_item.setFont(fixed_font(10))
                    self.recent.setItem(row, column, recent_item)
        preferences = self._address_preferences()
        self.address_rows = [item for item in data["addresses"] if not preferences.get(item["address"], {}).get("hidden") ]
        self.addresses.setRowCount(len(self.address_rows))
        for row, address in enumerate(self.address_rows):
            for column, value in enumerate([address.get("label", ""), address["address"], ("✓" if preferences.get(address["address"], {}).get("used", address.get("amount", 0) > 0) else "—")]):
                item = QTableWidgetItem(value)
                if column in (1, 2):
                    item.setFont(fixed_font(10))
                if column == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    font = item.font()
                    font.setPointSize(18)
                    item.setFont(font)
                self.addresses.setItem(row, column, item)
        self.page_label.setText(f"{len(self.rows)} entries  ·  page {self.skip // 100 + 1}")
        self._style_transaction_values()
        self.filter_history()
        self.network.setText(("● Tor only" if self.tor_enabled and self.tor.bootstrapped else
                              "○ Tor unavailable · no direct fallback" if self.tor_enabled else "● Direct connection")
                             + f" · block {chain['blocks']:,}")
        if info.get("scanning"):
            message = "Core is rescanning. Wallet balances and activity may be incomplete."
        elif chain.get("initialblockdownload"):
            message = f"Core is syncing · {float(chain.get('verificationprogress', 0)) * 100:.1f}% verified · balances may be incomplete"
        else:
            message = f"Wallet updated at {datetime.now():%H:%M:%S} · local Core connection"
        self.statusBar().showMessage(message)

    def filter_history(self):
        query = self.search.text().casefold()
        for row, tx in enumerate(self.rows):
            self.transactions.setRowHidden(row, query not in json.dumps(tx, default=str).casefold())
        self.transactions.set_empty_message("No matching activity" if query else "No activity yet",
                                            "Try a different search." if query else "Wallet transactions will appear here.")
        self.transactions.update_empty_state()

    def paginate(self, delta):
        if not self.busy and self.service:
            self.skip = max(0, self.skip + delta)
            self.refresh()

    def generate(self):
        if not self.service or not self.wallet_picker.currentText():
            self.statusBar().showMessage("Connect and select a wallet first.")
            return
        if self.busy:
            QTimer.singleShot(150, lambda: self.generate() if self.tabs.currentIndex() == 4 and not self.address.text() else None)
            return
        service, name, text = self.service, self.wallet_picker.currentText(), self.receive_label.text()
        self.task("Requesting an address from Core…", lambda: service.receive(name, text), self.received)

    def _reset_receive(self):
        self.address.clear()
        self.receive_qr.clear()
        self.receive_visual.setCurrentIndex(0)
        self.receive_details.hide()
        self.receive_mark_used.setChecked(False)
        self.receive_label.clear()
        self.receive_label.setReadOnly(False)
        self.receive_used.hide()
        self.receive_done.hide()
        self.generate_button.show()

    def _open_receive(self):
        self._reset_receive()
        self.tabs.setCurrentIndex(4)
        QTimer.singleShot(0, self.generate)

    def received(self, result):
        self.address.setText(result[0])
        self.receive_qr.setPixmap(self._qr_pixmap(result[0], size=320))
        self.receive_visual.setCurrentIndex(1)
        self.receive_details.show()
        self.receive_used.show()
        self.receive_label.setReadOnly(False)
        self.receive_done.show()
        self.generate_button.hide()
        self.statusBar().showMessage("Address generated by Core. Verify independently before use.")

    _qr_pixmap = staticmethod(qr_pixmap)

    def copy_address(self):
        address = self.address.text()
        if not address:
            self.statusBar().showMessage("Generate an address first.")
            return
        QApplication.clipboard().setText(address)
        self.statusBar().showMessage("Address copied. Verify the complete pasted address before use.")


    def transaction_details(self, row, column):
        self.show_text("Wallet activity entry", json.dumps(self.rows[row], indent=2, default=str))

    def address_details(self, row, column):
        record = self.address_rows[row]
        address = record["address"]
        dialog, layout = self._dialog("Wallet address", size=(840, 620), online=True)
        qr = QLabel()
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr.setPixmap(self._qr_pixmap(address, size=320))
        layout.addWidget(qr)
        value = QLineEdit(address)
        value.setReadOnly(True)
        value.setFont(fixed_font(10))
        layout.addWidget(value)
        name = QLineEdit(record.get("label", ""))
        name.setPlaceholderText("Label (optional)")
        layout.addWidget(name)
        used = QCheckBox("Mark as used")
        used.setStyleSheet("QCheckBox::indicator { width: 22px; height: 22px; }")
        used.setChecked(self._address_preferences().get(address, {}).get("used", record.get("amount", 0) > 0))
        layout.addWidget(used)
        footer = QHBoxLayout()
        def remove():
            if QMessageBox.question(dialog, "Remove address from list?",
                "This address will remain part of the Core wallet and can still receive bitcoin.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
                self._store_address_preference(address, hidden=True)
                dialog.accept()
                self.refresh()
        footer.addWidget(button("Remove address", remove))
        footer.addStretch()
        def save():
            service, wallet = self.service, self.wallet_picker.currentText()
            self._store_address_preference(address, used=used.isChecked())
            label_value = name.text()
            self.task("Saving address label…", lambda: service.rpc.call("setlabel", [address, label_value], wallet=wallet),
                      lambda _: (dialog.accept(), self.refresh()))
        footer.addWidget(button("Done", save, True))
        layout.addLayout(footer)
        self._dialog_help(dialog)
        dialog.exec()

    def show_text(self, title, content):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(900, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(content)
        text.setReadOnly(True)
        layout.addWidget(text)
        layout.addWidget(button("Close", dialog.accept))
        dialog.exec()

    def about(self):
        self.show_text("About Core Companion", f"Core Companion {__version__}\n\nLinux release candidate · independent security review pending.\n\nBitcoin Core handles wallets, addresses and PSBT signing. The online view is watch-only. The cold signer uses a temporary Core process in RAM.\n\nPython / Qt Widgets. No browser engine, telemetry or local web server.")

    def closeEvent(self, event):
        if self.tor_install_process is not None:
            self.statusBar().showMessage("Wait for Tor installation to finish before closing.")
            event.ignore()
            return
        if self.core_download_process is not None:
            answer = QMessageBox.question(
                self,
                "Core download is running",
                "Stop the download and verification before closing Companion?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.core_download_closing = True
            process = self.core_download_process
            if process.state() == QProcess.ProcessState.NotRunning:
                self._finish_core_download_ui(process)
                QTimer.singleShot(0, self.close)
            else:
                self.cancel_core_download()
            event.ignore()
            return
        if not self.cold_session:
            if self.tor_enabled and not self._stop_managed_node():
                event.ignore()
                return
            self.tor_pending = None
            self.tor.stop()
            event.accept()
            return
        answer = QMessageBox.warning(
            self,
            "Cold signer is active",
            "Closing the main app will close the cold signer and stop its temporary Core process. "
            + ("Swap will be restored; host networking was left on."
               if self.dev_keep_network else "Swap will be restored after those processes stop. Networking remains permanently disabled."),
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Close,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Close:
            event.ignore()
            return
        if not self._stop_cold_process_group():
            QMessageBox.critical(
                self,
                "Cold Core is still running",
                ("The temporary Core process did not stop. Swap remains disabled; host networking was left on. "
                 if self.dev_keep_network else
                 "The temporary Core process did not stop. Networking and swap remain disabled. ")
                + "Close the cold signer process before closing this app.",
            )
            event.ignore()
            return
        self._restore_cold_system()
        if self.cold_session:
            event.ignore()
        else:
            event.accept()


    def _go_back(self):
        self.recipient_scanner.stop()
        self.tabs.setCurrentIndex(0 if self.tabs.currentIndex() == 1 else 1 if self.tabs.currentIndex() == 7 else 2)

    def _address_preferences(self):
        wallet = self.wallet_picker.currentText()
        endpoint = str(self.service.rpc.cookie_path) if self.service else ""
        self.address_settings_key = "addresses/" + hashlib.sha256((endpoint + "/" + wallet).encode()).hexdigest()
        try:
            value = json.loads(QSettings("CoreCompanion", "CoreCompanion").value(self.address_settings_key, "{}"))
            return {key: item for key, item in value.items() if isinstance(key, str) and isinstance(item, dict)} if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _store_address_preference(self, address, **values):
        preferences = self._address_preferences()
        preferences.setdefault(address, {}).update(values)
        QSettings("CoreCompanion", "CoreCompanion").setValue(self.address_settings_key, json.dumps(preferences))

    def _finish_receive(self):
        address = self.address.text()
        if not address or not self.service:
            return
        self._store_address_preference(address, used=self.receive_mark_used.isChecked())
        service, wallet, text = self.service, self.wallet_picker.currentText(), self.receive_label.text()
        self.task("Saving label…", lambda: service.rpc.call("setlabel", [address, text], wallet=wallet),
                  lambda _: (self.tabs.setCurrentIndex(2), self.refresh()))

    def _send(self):
        page = self.page("Send")
        self._wallet_page_heading(page, "Send Bitcoin", "Create an unsigned transaction for your cold signer.")
        panel = QFrame()
        panel.setObjectName("FormPanel")
        form = QFormLayout(panel)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(16)
        recipient_row = QHBoxLayout()
        self.send_recipient = QLineEdit()
        self.send_recipient.setToolTip("Recipient Bitcoin address. Scan a Bitcoin payment QR or paste the address.")
        self.send_recipient.setPlaceholderText("Recipient address")
        recipient_row.addWidget(self.send_recipient, 1)
        self.recipient_scanner = QRScanner(self)
        recipient_row.addWidget(button("Scan QR", self.recipient_scanner.scan))
        self.recipient_scanner.decoded.connect(self._recipient_scanned)
        self.recipient_scanner.failed.connect(lambda message: QMessageBox.warning(self, "QR scanner", message))
        form.addRow("Recipient", recipient_row)
        self.send_amount = QLineEdit()
        self.send_amount.setToolTip("Amount in BTC, with up to 8 decimal places. Core calculates the final fee and change.")
        self.send_amount.setPlaceholderText("0.00000000")
        form.addRow("Amount · BTC", self.send_amount)
        self.send_fee = QLineEdit("2")
        self.send_fee.setToolTip("Fee rate in satoshis per virtual byte. Core performs coin selection and fee calculation.")
        form.addRow("Fee rate · sat/vB", self.send_fee)
        page.addWidget(panel)
        page.addStretch()
        page.addWidget(button("Review transaction", self._create_psbt, True), 0, Qt.AlignmentFlag.AlignRight)

    def _recipient_scanned(self, text):
        if text.lower().startswith("bitcoin:"):
            uri = urlsplit(text)
            fields = parse_qs(uri.query)
            if any(key.startswith("req-") for key in fields):
                QMessageBox.warning(self, "Unsupported payment request", "This QR requires additional payment fields.")
                return
            self.send_recipient.setText(uri.path)
            if fields.get("amount"):
                self.send_amount.setText(fields["amount"][0])
        else:
            self.send_recipient.setText(text)

    def _create_psbt(self):
        if not self.service or not self.wallet_picker.currentText():
            return
        service, wallet = self.service, self.wallet_picker.currentText()
        recipient, amount, fee = self.send_recipient.text().strip(), self.send_amount.text(), self.send_fee.text()
        self.task("Core is funding the transaction…", lambda: service.create_psbt(wallet, recipient, amount, fee),
                  lambda result: self._review_transaction(result["decoded"]["tx"], "Review unsigned transaction",
                    "Export unsigned PSBT", lambda: self._export_psbt(result["psbt"]),
                    fee=result.get("fee"), change=result.get("changepos")))

    def _review_transaction(self, transaction, title, action, callback, *, fee=None, change=None, allowed=True):
        dialog, layout = self._dialog(title, "Check every output before continuing.", size=(940, 710), online=True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        outputs = QVBoxLayout(body)
        for index, output in enumerate(transaction.get("vout", [])):
            script = output.get("scriptPubKey", {})
            address = script.get("address") or script.get("hex") or "Unknown script"
            card = QFrame()
            card.setObjectName("FormPanel")
            row = QVBoxLayout(card)
            row.addWidget(label(("Change" if index == change else "Output " + str(index + 1)) + " · " + btc(output["value"]) + " BTC", "Heading"))
            full = label(address)
            full.setWordWrap(True)
            full.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(full)
            outputs.addWidget(card)
        if fee is not None:
            outputs.addWidget(label("Fee · " + btc(fee) + " BTC", "Heading"))
        detail = QPlainTextEdit(json.dumps(transaction, indent=2, default=str))
        detail.setReadOnly(True)
        detail.hide()
        details = QCheckBox("Show Core details")
        details.toggled.connect(detail.setVisible)
        outputs.addWidget(details)
        outputs.addWidget(detail)
        outputs.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        if not allowed:
            layout.addWidget(label("Core rejected this transaction for the mempool. Check the details before retrying.", "InfoStrip"))
        footer = QHBoxLayout()
        footer.addWidget(button("Cancel", dialog.reject))
        footer.addStretch()
        def proceed():
            dialog.accept()
            callback()
        proceed_button = button(action, proceed, True)
        proceed_button.setEnabled(allowed)
        footer.addWidget(proceed_button)
        layout.addLayout(footer)
        self._dialog_help(dialog)
        dialog.exec()

    def _export_psbt(self, psbt):
        dialog, layout = self._dialog("Unsigned PSBT", "Scan with your cold signer, or save to a file.", size=(820, 740), online=True)
        qr = QLabel()
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        try:
            qr.setPixmap(self._qr_pixmap(psbt, size=440))
        except (ValueError, OverflowError, DataOverflowError):
            qr.setText("This PSBT is too large for one QR. Save the file instead.")
        layout.addWidget(qr, 1)
        text = QPlainTextEdit(psbt)
        text.setReadOnly(True)
        text.setMaximumHeight(95)
        layout.addWidget(text)
        def save():
            path, _ = QFileDialog.getSaveFileName(dialog, "Save unsigned PSBT", "unsigned.psbt", "PSBT files (*.psbt)")
            if path:
                try:
                    Path(path).write_bytes(base64.b64decode(psbt, validate=True))
                except (OSError, ValueError) as exc:
                    QMessageBox.warning(dialog, "Could not save PSBT", str(exc))
        footer = QHBoxLayout()
        footer.addWidget(button("Save PSBT…", save))
        footer.addStretch()
        footer.addWidget(button("Done", dialog.accept, True))
        layout.addLayout(footer)
        self._dialog_help(dialog)
        dialog.exec()

    def _import_psbt_dialog(self):
        if not self.service or not self.wallet_picker.currentText():
            return
        dialog, layout = self._dialog("Import PSBT", "Review the signed transaction before broadcasting.", size=(820, 560), online=True)
        text = QPlainTextEdit()
        text.setPlaceholderText("Scan, paste, or load the signed PSBT")
        text.setToolTip("A signed PSBT from your signer. Importing only asks Core to finalize and check it; broadcasting requires a separate approval.")
        layout.addWidget(text, 1)
        scanner = QRScanner(dialog)
        scanner.decoded.connect(text.setPlainText)
        scanner.failed.connect(lambda message: QMessageBox.warning(dialog, "QR scanner", message))
        def load():
            path, _ = QFileDialog.getOpenFileName(dialog, "Open PSBT", "", "PSBT files (*.psbt);;All files (*)")
            if not path:
                return
            try:
                with Path(path).open("rb") as stream:
                    data = stream.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise ValueError("PSBT exceeds the 2 MiB limit.")
                text.setPlainText(base64.b64encode(data).decode() if data.startswith(b"psbt\xff") else data.decode("ascii").strip())
            except (OSError, ValueError) as exc:
                QMessageBox.warning(dialog, "Could not load PSBT", str(exc))
        row = QHBoxLayout()
        row.addWidget(button("Scan QR", scanner.scan))
        row.addWidget(button("Load file…", load))
        row.addStretch()
        layout.addLayout(row)
        def review():
            psbt = text.toPlainText().strip()
            if not psbt or len(psbt) > 2 * 1024 * 1024:
                QMessageBox.warning(dialog, "PSBT required", "Load a PSBT smaller than 2 MiB.")
                return
            service, wallet = self.service, self.wallet_picker.currentText()
            scanner.stop()
            dialog.accept()
            self.task("Core is checking the signed PSBT…", lambda: service.finalize_psbt(wallet, psbt), self._review_finalized)
        footer = QHBoxLayout()
        footer.addWidget(button("Back", dialog.reject))
        footer.addStretch()
        footer.addWidget(button("Review transaction", review, True))
        layout.addLayout(footer)
        self._dialog_help(dialog)
        dialog.exec()
        scanner.stop()

    def _review_finalized(self, result):
        acceptance = result["acceptance"][0]
        service = self.service
        transaction_hex = result["hex"]
        fee = acceptance.get("fees", {}).get("base")
        self._review_transaction(result["transaction"], "Review signed transaction", "Broadcast transaction",
            lambda: self.task("Broadcasting through Core…", lambda: service.broadcast(transaction_hex),
                              lambda txid: (self.show_text("Transaction broadcast", txid), self.refresh())),
            fee=fee, allowed=acceptance.get("allowed") is True)


    def _privacy_toggled(self, enabled):
        if enabled == self.tor_enabled:
            return
        if not self._allow_online() or self.busy or self.core_download_process is not None or self.tor_install_process is not None:
            self.statusBar().showMessage("Finish the current operation before changing network privacy.")
            accepted = False
        else:
            accepted = True
            if not enabled:
                accepted = QMessageBox.warning(self, "Disable Tor protection?",
                    "Core downloads and blockchain connections will use the internet directly. "
                    "Download services and Bitcoin peers can see your public IP and link activity to it. "
                    "The managed node will stop; reconnect to use the new setting.",
                    QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                    QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes
            if accepted:
                accepted = self._stop_managed_node()
        if accepted:
            self.tor_pending = None
            self.tor.stop()
            self.disconnect()
            self.tor_enabled = enabled
            self.port.setReadOnly(enabled)
            settings = QSettings("CoreCompanion", "CoreCompanion")
            settings.setValue("network/torOnly", enabled)
            settings.sync()
            self._set_core_status("Tor only selected" if enabled else "Direct connection selected")
            self.statusBar().showMessage("Network privacy saved. Connect when ready.")
        self.tor_choice.blockSignals(True)
        self.tor_choice.setChecked(self.tor_enabled)
        self.tor_choice.blockSignals(False)

    def _privacy_dialog(self):
        if not self._allow_online():
            return
        dialog, layout = self._dialog("Network privacy", "Choose how this installation connects.", size=(620, 360))
        choice = QCheckBox("Tor only (recommended)")
        choice.setChecked(self.tor_enabled)
        choice.setToolTip(self.tor_choice.toolTip())
        layout.addWidget(choice)
        text = label("Downloads, signing keys and the managed node use Tor. If Tor stops, connections stop. "
                     "Other apps and separately running nodes keep their own settings.", "Muted")
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addStretch()
        row = QHBoxLayout()
        row.addWidget(button("Cancel", dialog.reject))
        row.addStretch()
        def apply():
            self._privacy_toggled(choice.isChecked())
            if self.tor_enabled == choice.isChecked():
                dialog.accept()
        row.addWidget(button("Apply", apply, True))
        layout.addLayout(row)
        self._dialog_help(dialog)
        dialog.exec()

    def _ensure_tor(self, action):
        if not self.tor_enabled:
            return True
        if not self._allow_online() or self.cold_session:
            return False
        if self.tor.bootstrapped:
            return True
        self.tor_pending = action
        if self.tor_install_process is not None:
            return False
        if not _system_tool("tor") or not _system_tool("curl"):
            self._install_tor()
            return False
        try:
            self.tor.start()
            self._set_core_status("Connecting to Tor…")
            self.network.setText("○ Tor connecting · no direct fallback")
        except (ValueError, OSError) as exc:
            self.tor_pending = None
            QMessageBox.warning(self, "Tor could not start", str(exc))
        return False

    def _tor_ready(self):
        if not self._allow_online() or not self.tor_enabled:
            self.tor.stop()
            self.tor_pending = None
            return
        action, self.tor_pending = self.tor_pending, None
        self._set_core_status("Tor connected · no direct fallback")
        self.network.setText("● Tor only")
        if action:
            QTimer.singleShot(0, action)

    def _tor_unavailable(self, message):
        self.tor_pending = None
        if self.tor_enabled:
            if self.core_download_process is not None:
                self.cancel_core_download()
            self._set_core_status("Tor unavailable · direct access blocked", "error")
            self.network.setText("○ Tor unavailable · no direct fallback")
            self.statusBar().showMessage(message)

    def _install_tor(self):
        if not self._allow_online():
            return
        if sys.platform != "linux" or not _system_tool("apt-get") or not _system_tool("pkexec"):
            self.tor_pending = None
            QMessageBox.warning(self, "Tor installation", "Automatic installation requires Debian, apt and administrator authorization.")
            return
        answer = QMessageBox.question(self, "Install Tor?",
            "Tor or curl was not found. Install them from this computer's signed Debian repositories? "
            "This bootstrap uses a direct connection and requires administrator authorization. "
            "Bitcoin downloads and node startup will wait until Tor is connected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            self.tor_pending = None
            return
        self._tor_install_stage("update")

    def _tor_install_stage(self, stage):
        if not self._allow_online():
            self.tor_pending = None
            return
        process = QProcess(self)
        self.tor_install_process = process
        self.tor_install_output = ""
        environment = QProcessEnvironment()
        environment.insert("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        environment.insert("LANG", "C")
        for key in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY"):
            if os.environ.get(key):
                environment.insert(key, os.environ[key])
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self._tor_install_read(process))
        process.finished.connect(lambda code, _: self._tor_install_finished(process, stage, code))
        process.errorOccurred.connect(lambda error: self._tor_install_finished(process, stage, -1)
                                     if error == QProcess.ProcessError.FailedToStart else None)
        arguments = [_system_tool("apt-get"), "-o", "Acquire::AllowInsecureRepositories=false",
                     "-o", "Acquire::AllowDowngradeToInsecureRepositories=false",
                     "-o", "APT::Get::AllowUnauthenticated=false",
                     "-o", "APT::Update::Error-Mode=any"]
        arguments += ["update"] if stage == "update" else ["-y", "--no-install-recommends", "install", "tor", "curl"]
        self._set_core_status("Preparing Tor installation…" if stage == "update" else "Installing Tor and curl…")
        process.start(_system_tool("pkexec"), arguments)

    def _tor_install_read(self, process):
        if process is self.tor_install_process:
            self.tor_install_output = (self.tor_install_output + bytes(process.readAllStandardOutput()).decode("utf-8", "replace"))[-6000:]

    def _tor_install_finished(self, process, stage, code):
        if process is not self.tor_install_process:
            return
        self._tor_install_read(process)
        self.tor_install_process = None
        process.deleteLater()
        if code:
            self.tor_pending = None
            self._set_core_status("Tor installation did not finish · Bitcoin traffic blocked", "error")
            QMessageBox.warning(self, "Tor was not installed", self.tor_install_output[-2000:] or "Administrator authorization or installation failed.")
            return
        if stage == "update":
            self._tor_install_stage("install")
            return
        if not _system_tool("tor") or not _system_tool("curl"):
            self.tor_pending = None
            self._set_core_status("Tor is still unavailable · Bitcoin traffic blocked", "error")
            return
        action = self.tor_pending
        if action:
            self._ensure_tor(action)

    def _stop_managed_node(self):
        process = self.managed_core_process
        if process is not None and process.poll() is None:
            self._set_core_status("Stopping Bitcoin Core safely…")
            try:
                process.terminate()
                process.wait(timeout=15)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                self.statusBar().showMessage("Core is still stopping. Wait, then try again; network privacy has not changed.")
                return False
        self.managed_core_process = None
        self.managed_node_tor_proxy = None
        self.node_start_timer.stop()
        return True

    def _lock_cold_installation(self):
        self.permanent_cold = PermanentAirgap.is_committed()
        self.cold_required = True
        self.online_choice.setEnabled(False)
        self.tor_choice.setEnabled(False)
        self.download_button.setEnabled(False)
        self.connection.hide()
        self.sync_timer.stop()
        self.node_start_timer.stop()
        self.connection_fallback = False
        self.service = None
        self.mode_indicator.setText("PERMANENT COLD")
        self.mode_indicator.setProperty("mode", "cold")
        self._set_core_status("Permanent cold installation · online functions disabled")
        self.network.setText("○ Offline protection requires verification")
        self.statusBar().showMessage("Never reconnect this computer after using a real wallet. Remove networking hardware for the strongest safeguard.")

    def _allow_online(self):
        if self.cold_required or PermanentAirgap.is_committed():
            self._lock_cold_installation()
            self.statusBar().showMessage("Online functions are permanently blocked on this cold installation.")
            return False
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bitcoin Core wallet companion")
    parser.add_argument("--version", action="version", version=f"Core Companion {__version__}")
    parser.add_argument("--cold-helper", action="store_true")
    parser.add_argument("--bitcoind")
    parser.add_argument("--session-id")
    parser.set_defaults(dev_keep_network=False)
    if DEVELOPMENT_BUILD:
        parser.add_argument(
            "--dev-keep-network", action="store_true",
            help="development only: leave host networking enabled during cold signer sessions",
        )
    args = parser.parse_args(argv)
    if args.dev_keep_network and PermanentAirgap.is_committed():
        parser.error("This computer is committed to permanent offline mode. The development network bypass is forbidden.")
    application = QApplication(["core-companion"])
    application.setApplicationName("Core Companion")
    application.setOrganizationName("CoreCompanion")
    application.setDesktopFileName("core-companion")
    application.setWindowIcon(QIcon(str(Path(__file__).with_name("icon.svg"))))
    application.setStyle("Fusion")
    application.setQuitOnLastWindowClosed(True)
    if args.cold_helper:
        if not args.bitcoind or not args.session_id or re.fullmatch(r"[0-9a-f]{32}", args.session_id) is None:
            parser.error("--cold-helper requires --bitcoind and a valid --session-id")
        from .cold_ui import ColdSignerDialog
        dialog = ColdSignerDialog(args.bitcoind, args.session_id, dev_keep_network=args.dev_keep_network)
        if dialog.core is None:
            return
        dialog.show()
        print("COLD_SIGNER_READY", flush=True)
        application.exec()
        return
    window = App(dev_keep_network=args.dev_keep_network)
    window.show()
    if window.cold_required:
        window._set_core_status("Permanent cold installation · online functions disabled")
    elif window._installed_core_binary() or default_cookie_path().is_file():
        window._set_core_status("Choose network privacy, then connect to Bitcoin Core.")
    else:
        window._set_core_status("Choose network privacy, then download and verify Core.")
    application.exec()
