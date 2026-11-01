"""Qt desktop views; Core access remains in wallet.py and rpc.py."""
import argparse
import json
import os
import queue
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QProcess, QTimer, QEvent, QRect
from PySide6.QtGui import QAction, QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget, QDialog,
    QFormLayout, QPlainTextEdit, QFrame, QProgressBar, QToolTip,
    QSizePolicy)
from PySide6.QtWidgets import QMessageBox
import qrcode
from .rpc import CoreError, CoreRPC
from .wallet import WalletService, btc
from .linux_cold import ColdSetupError, ColdSystemSession
from .theme import stylesheet
from .widgets import ActionRow, ChoiceRow, IconButton, LineIcon

MANAGED_RPC_PORT = 8332
PRUNE_TARGET_MIB = 10000

def label(text, name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    return widget

def button(text, action, primary=False):
    widget = QPushButton(text)
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
    shell = QVBoxLayout(page)
    shell.setContentsMargins(0, 0, 0, 0)
    content = QWidget()
    content.setObjectName("PageContent")
    content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    shell.addWidget(content, 1)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(30, top, 30, bottom)
    layout.setSpacing(14)
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
        self.core_download_process = None
        self.core_download_stderr = ""
        self.downloaded_bitcoind = None
        self.core_download_closing = False
        self.core_download_cancelled = False
        self.core_cookie_path = None
        self.connection_fallback = False
        self.pending_cold_start = False
        self.managed_core_process = None
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
        self._set_core_status("Looking for Bitcoin Core…")
    def _menus(self):
        menu = self.menuBar().addMenu("Wallet")
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

    def _layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 10, 20, 12)
        root.setSpacing(8)
        toolbar = QHBoxLayout()
        mark = label("₿", "Mark")
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(mark)
        toolbar.addWidget(label("Core Companion", "Brand"))
        toolbar.addStretch()
        self.help_button = IconButton(
            "i", "Help", self._toggle_help_mode,
            tooltip="Turn on instant explanations. Hover over a control to see what it does.",
        )
        toolbar.addWidget(self.help_button)
        self.theme_button = IconButton("dark", "Dark mode", self._toggle_theme)
        toolbar.addWidget(self.theme_button)
        toolbar.addWidget(IconButton("node", "Connection", self.show_connection))
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
        self.network = label("○  Offline", "Muted")
        self.statusBar().addPermanentWidget(self.network)
        self.cold_button_top = self.mode_continue
        if sys.platform != "linux":
            self.cold_choice.setEnabled(False)
            self.cold_choice.setToolTip("The cold signer is available on Linux in this first release.")
        self.tabs.setCurrentIndex(0)

    def _welcome(self):
        page, layout = page_layout(30, 24, "OnboardingPage")
        layout.addWidget(label("Welcome", "Eyebrow"))
        layout.addWidget(label("Bitcoin Core", "Title"))
        intro = label(
            "Companion checks for Bitcoin Core on this computer. Your node and wallet data stay local.",
            "Muted",
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)
        card_layout.addWidget(label("LOCAL NODE", "Eyebrow"))
        self.core_status = label("Checking for Bitcoin Core…", "CoreStatus")
        card_layout.addWidget(self.core_status)
        card_layout.addWidget(label(
            "Core connects to Bitcoin and keeps the node data on this computer.",
            "Muted",
        ))
        row = QHBoxLayout()
        row.addWidget(button("Connect to Bitcoin Core", self.connect, True))
        self.download_button = button("Download & verify Bitcoin Core", self.download_bitcoin_core)
        self.download_button.setToolTip(
            "Downloads Core and its pinned signer keys, verifies the release, then installs it."
        )
        row.addWidget(self.download_button)
        card_layout.addLayout(row)
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
        advanced.addWidget(button("Advanced connection settings…", self.show_connection))
        advanced.addStretch()
        card_layout.addLayout(advanced)
        layout.addWidget(card)
        layout.addStretch()
        continue_row = QHBoxLayout()
        continue_row.addStretch()
        continue_row.addWidget(button("Choose wallet mode  →", lambda: self.tabs.setCurrentIndex(1), True))
        layout.addLayout(continue_row)
        self.tabs.addTab(page, "Welcome")

    def _set_core_status(self, text, state="idle"):
        self.core_status.setText(text)
        self.core_status.setProperty("state", state)
        self.core_status.style().unpolish(self.core_status)
        self.core_status.style().polish(self.core_status)
        self.core_status.update()

    def _mode_page(self):
        page, layout = page_layout(28, 24, "OnboardingPage")
        layout.addWidget(label("Choose a wallet mode", "Title"))
        choices = QVBoxLayout()
        choices.setSpacing(0)
        self.cold_choice = ChoiceRow("❄", "Cold storage (private keys)", accent="blue")
        self.cold_choice.clicked.connect(lambda: self._select_mode("cold"))
        self.online_choice = ChoiceRow("◉", "Online node (watch only)", accent="red")
        self.online_choice.clicked.connect(lambda: self._select_mode("online"))
        choices.addWidget(self.cold_choice)
        divider = QHBoxLayout()
        divider.setContentsMargins(0, 5, 0, 5)
        divider.addStretch(1)
        left_rule = QFrame()
        left_rule.setFrameShape(QFrame.Shape.HLine)
        left_rule.setObjectName("ChoiceDivider")
        right_rule = QFrame()
        right_rule.setFrameShape(QFrame.Shape.HLine)
        right_rule.setObjectName("ChoiceDivider")
        divider.addWidget(left_rule, 1)
        divider.addWidget(label("OR", "Muted"))
        divider.addWidget(right_rule, 1)
        choices.addLayout(divider)
        choices.addWidget(self.online_choice)
        layout.addLayout(choices)
        layout.addStretch()
        row = QHBoxLayout()
        row.addWidget(button("‹  Back", lambda: self.tabs.setCurrentIndex(0)))
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
            "Cold signer test mode" if self.dev_keep_network else "Keep this computer offline",
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
            "Computer networking stays on" if self.dev_keep_network else "Network access will be disabled",
            "NoticeTitle",
        ))
        if self.dev_keep_network:
            detail = "Bitcoin Core peer networking remains off. Swap is still disabled. Use test wallets only."
        else:
            detail = "Swap will also be disabled. Close other programs first; on a low-memory computer, the desktop may freeze."
        notice_copy.addWidget(label(detail, "Muted"))
        notice_layout.addLayout(notice_copy, 1)
        layout.addWidget(notice)
        layout.addStretch(1)
        footer = QHBoxLayout()
        footer.addWidget(button("‹  Back", self._back_from_cold_notice))
        footer.addStretch()
        continue_button = button("Continue", self._begin_cold_signer, True)
        continue_button.setObjectName("ColdContinue")
        footer.addWidget(continue_button)
        layout.addLayout(footer)
        self.tabs.addTab(page, "Cold storage")

    def _back_from_cold_notice(self):
        self.tabs.setCurrentIndex(self.cold_notice_previous)

    def _online_home(self):
        page, layout = page_layout(18, 16, "OnlinePage")
        layout.setSpacing(10)
        title_row = QHBoxLayout()
        title_row.addWidget(label("Watch-only wallet", "Eyebrow"))
        title_row.addStretch()
        self.wallet_picker = QComboBox()
        self.wallet_picker.setMinimumWidth(210)
        self.wallet_picker.currentTextChanged.connect(self.select_wallet)
        title_row.addWidget(self.wallet_picker)
        self.online_name = label("Connect to Bitcoin Core", "Title")
        layout.addLayout(title_row)
        layout.addWidget(self.online_name)
        sync_card = QFrame()
        sync_card.setObjectName("Card")
        sync_layout = QVBoxLayout(sync_card)
        sync_layout.setContentsMargins(15, 11, 15, 11)
        sync_layout.setSpacing(6)
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
        self.sync_progress.setFixedHeight(8)
        sync_layout.addWidget(self.sync_progress)
        layout.addWidget(sync_card)
        kpis = QHBoxLayout()
        self.balance = self._kpi(kpis, "Balance", "— BTC")
        self.pending = self._kpi(kpis, "Unconfirmed", "— BTC")
        self.immature = self._kpi(kpis, "Wallet", "Watch-only")
        layout.addLayout(kpis)
        actions = QGridLayout()
        actions.setHorizontalSpacing(9)
        actions.setVerticalSpacing(9)
        receive_action = ActionRow(
            "↓", "Receive Bitcoin", "", primary=True,
            tooltip="Create an address and QR code using Bitcoin Core.",
        )
        receive_action.clicked.connect(self._open_receive)
        send_action = ActionRow(
            "⇧", "Wallet activity", "",
            tooltip="Review wallet transactions and confirmations.", icon_key="activity",
        )
        send_action.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        addresses_action = ActionRow(
            "▣", "View addresses & labels", "",
            tooltip="Browse addresses known to the selected Core wallet.",
        )
        addresses_action.clicked.connect(lambda: self.tabs.setCurrentIndex(5))
        tools_action = ActionRow(
            "⚙", "Tools & Settings", "",
            tooltip="Inspect a PSBT or start a separate cold signer session.",
        )
        tools_action.clicked.connect(lambda: self.tabs.setCurrentIndex(6))
        for index, action in enumerate((receive_action, send_action, addresses_action, tools_action)):
            actions.addWidget(action, index // 2, index % 2)
        layout.addLayout(actions)
        activity_header = QHBoxLayout()
        activity_header.addWidget(label("Recent activity", "Heading"))
        activity_header.addStretch()
        activity_header.addWidget(button("All  →", lambda: self.tabs.setCurrentIndex(3)))
        layout.addLayout(activity_header)
        self.recent = self.table(["DATE", "LABEL", "AMOUNT · BTC"])
        self.recent.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.recent.setMaximumHeight(150)
        layout.addWidget(self.recent)
        layout.addWidget(label("Core owns the wallet data. Companion displays what Core reports.", "Muted"))
        self.tabs.addTab(page, "Wallet")

    def _kpi(self, parent_layout, heading, value):
        card = QFrame()
        card.setObjectName("KPI")
        column = QVBoxLayout(card)
        column.setContentsMargins(14, 10, 14, 10)
        column.setSpacing(5)
        column.addWidget(label(heading, "Muted"))
        result = label(value, "KPIValue")
        column.addWidget(result)
        parent_layout.addWidget(card, 1)
        return result

    def _select_mode(self, mode):
        self.mode_choice = mode
        self.cold_choice.setChecked(mode == "cold")
        self.online_choice.setChecked(mode == "online")
        self.mode_continue.setObjectName("ColdContinue" if mode == "cold" else "OnlineContinue")
        self.mode_continue.style().unpolish(self.mode_continue)
        self.mode_continue.style().polish(self.mode_continue)
        self.mode_continue.setEnabled(True)

    def _continue_mode(self):
        if self.mode_choice == "cold":
            self.start_cold_signer()
        elif self.mode_choice == "online":
            if self.service:
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
        self.help_button.set_caption("Help on" if self.help_mode else "Help")
        self.help_button.setProperty("active", self.help_mode)
        self.help_button.style().unpolish(self.help_button)
        self.help_button.style().polish(self.help_button)

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.setStyleSheet(stylesheet(self.dark_mode))
        self.theme_button.set_caption("Light mode" if self.dark_mode else "Dark mode")
        self.theme_button.set_glyph("light" if self.dark_mode else "dark")

    def _install_help_targets(self):
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QPushButton, QLineEdit, QComboBox, QPlainTextEdit, ActionRow)):
                if isinstance(widget, QPushButton):
                    text = widget.text()
                elif hasattr(widget, "placeholderText"):
                    text = widget.placeholderText()
                else:
                    text = ""
                if not widget.toolTip():
                    widget.setToolTip(f"{text or 'This setting'} on this screen.")
                widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Enter and self.help_mode and watched.toolTip():
            QToolTip.showText(watched.mapToGlobal(watched.rect().bottomLeft()), watched.toolTip(), watched)
        elif event.type() == QEvent.Type.Leave and self.help_mode:
            QToolTip.hideText()
        return super().eventFilter(watched, event)

    def page(self, title):
        widget, layout = page_layout(18, 16)
        self.tabs.addTab(widget, title)
        return layout

    def table(self, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(42)
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
        bar = QHBoxLayout()
        bar.addWidget(button("‹  Back to wallet", lambda: self.tabs.setCurrentIndex(2)))
        bar.addStretch()
        bar.addWidget(label("Transactions", "Heading"))
        bar.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search this page…")
        self.search.setMaximumWidth(250)
        self.search.textChanged.connect(self.filter_history)
        bar.addWidget(self.search)
        bar.addWidget(button("↻  Refresh", self.refresh))
        page.addLayout(bar)
        self.transactions = self.table(["STATUS", "DATE", "DESCRIPTION", "AMOUNT · BTC"])
        self.transactions.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col, width in [(0, 155), (1, 175), (3, 180)]:
            self.transactions.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.transactions.setColumnWidth(col, width)
        self.transactions.cellDoubleClicked.connect(self.transaction_details)
        page.addWidget(self.transactions, 1)
        bar = QHBoxLayout()
        self.page_label = label("No activity loaded", "Muted")
        bar.addWidget(self.page_label)
        bar.addStretch()
        bar.addWidget(button("‹  Newer", lambda: self.paginate(-100)))
        bar.addWidget(button("Older  ›", lambda: self.paginate(100)))
        page.addLayout(bar)
        page.addWidget(label("Double-click an entry for details. A transaction can have multiple wallet entries.", "Muted"))

    def _receive(self):
        page = self.page("Receive")
        page.addWidget(button("‹  Back to wallet", lambda: self.tabs.setCurrentIndex(2)))
        page.addWidget(label("Receive bitcoin", "Heading"))
        page.addWidget(label("Generate an address from the selected wallet’s policy in Bitcoin Core.", "Muted"))
        card = QFrame()
        card.setObjectName("Card")
        form = QVBoxLayout(card)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(10)
        form.addWidget(label("Label"))
        self.receive_label = QLineEdit()
        self.receive_label.setPlaceholderText("e.g. Savings")
        self.receive_label.setMaximumWidth(550)
        form.addWidget(self.receive_label)
        row = QHBoxLayout()
        self.generate_button = button("Generate address", self.generate, True)
        row.addWidget(self.generate_button)
        self.receive_done = button("Done", lambda: self.tabs.setCurrentIndex(2), True)
        self.receive_done.hide()
        row.addStretch()
        form.addLayout(row)
        form.addSpacing(8)
        form.addWidget(label("RECEIVE BITCOIN", "Eyebrow"))
        receive_content = QHBoxLayout()
        self.receive_qr = QLabel()
        self.receive_qr.setObjectName("QR")
        self.receive_qr.setFixedSize(190, 190)
        self.receive_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        receive_content.addWidget(self.receive_qr, 0, Qt.AlignmentFlag.AlignTop)
        address_column = QVBoxLayout()
        address_column.addWidget(label("ADDRESS", "Eyebrow"))
        self.address = QLineEdit()
        self.address.setReadOnly(True)
        self.address.setPlaceholderText("Your receiving address will appear here")
        self.address.setFont(QFont("Consolas", 11))
        address_column.addWidget(self.address)
        self.receive_used = label("✓  Used address", "Muted")
        self.receive_used.hide()
        address_column.addWidget(self.receive_used)
        row = QHBoxLayout()
        row.addWidget(button("Copy address", self.copy_address))
        row.addStretch()
        address_column.addLayout(row)
        address_column.addStretch()
        receive_content.addLayout(address_column, 1)
        form.addLayout(receive_content)
        page.addWidget(card)
        note = label("Verify the full address on your independent signer before depositing.", "Muted")
        note.setWordWrap(True)
        page.addWidget(note)
        page.addStretch()

    def _addresses(self):
        page = self.page("Addresses")
        row = QHBoxLayout()
        row.addWidget(button("‹  Back to wallet", lambda: self.tabs.setCurrentIndex(2)))
        row.addWidget(label("Receiving addresses", "Heading"))
        row.addStretch()
        row.addWidget(button("New address", self._open_receive))
        page.addLayout(row)
        page.addWidget(label("Known receiving addresses. Received amounts are lifetime totals, not spendable balances.", "Muted"))
        self.addresses = self.table(["DESCRIPTION", "ADDRESS", "RECEIVED · BTC"])
        self.addresses.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in [(0, 170), (2, 175)]:
            self.addresses.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.addresses.setColumnWidth(column, width)
        self.addresses.cellDoubleClicked.connect(self.address_details)
        page.addWidget(self.addresses, 1)
        page.addWidget(label("Change addresses and unissued descriptor addresses are not shown.", "Muted"))

    def _tools(self):
        page = self.page("Tools")
        page.addWidget(button("‹  Back to wallet", lambda: self.tabs.setCurrentIndex(2)))
        page.addWidget(label("Cold signer", "Heading"))
        page.addWidget(label("Create a BIP39 signing wallet in a temporary, offline Bitcoin Core session.", "Muted"))
        self.cold_button = button("Create cold signer wallet", self.start_cold_signer, True)
        if sys.platform != "linux":
            self.cold_button.setEnabled(False)
            self.cold_button.setToolTip("Linux cold-signer setup is the first target.")
        page.addWidget(self.cold_button)
        page.addSpacing(8)
        page.addWidget(label("Transaction inspection", "Heading"))
        page.addWidget(label("Inspect an existing PSBT with Core. This operation does not sign or broadcast.", "Muted"))
        self.psbt = QPlainTextEdit()
        self.psbt.setPlaceholderText("Paste a base64 PSBT…")
        self.psbt.setMaximumHeight(100)
        page.addWidget(self.psbt)
        row = QHBoxLayout()
        row.addWidget(button("Inspect PSBT", self.inspect, True))
        row.addStretch()
        page.addLayout(row)
        page.addSpacing(8)
        page.addWidget(label(
            "Cold signing runs in a separate temporary Bitcoin Core process. "
            "PSBT review and signing happen there; the online node view does not handle private keys.",
            "Muted",
        ))
        page.addStretch()

    def _connection_dialog(self):
        self.connection = QDialog(self)
        self.connection.setWindowTitle("Advanced connection · Core Companion")
        self.connection.setMinimumWidth(580)
        layout = QVBoxLayout(self.connection)
        layout.setContentsMargins(24, 24, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(label("Advanced connection", "Heading"))
        layout.addWidget(label(
            "Use these options only if automatic local detection does not work.", "Muted",
        ))
        form = QFormLayout()
        form.setSpacing(12)
        self.port = QLineEdit("8332")
        form.addRow("Core port", self.port)
        layout.addLayout(form)
        note = label(
            "Companion finds Core's local connection automatically. Keep Core running on this computer "
            "with local RPC enabled. Only loaded watch-only wallets appear.",
            "Muted",
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(button("Disconnect", self.disconnect))
        row.addStretch()
        row.addWidget(button("Connect", self.connect, True))
        layout.addLayout(row)

    def show_connection(self):
        if self.tabs.currentIndex() not in (0, 1):
            self.connection_purpose = "online"
        self.connection.show()
        self.connection.raise_()
        self.connection.activateWindow()

    def _installed_core_binary(self):
        root = companion_data_dir() / "bitcoin-core"
        binaries = [path for path in root.glob("*/bin/bitcoind") if path.is_file() and os.access(path, os.X_OK)]
        return max(binaries, key=lambda path: path.stat().st_mtime) if binaries else None

    def download_bitcoin_core(self):
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
        missing = [tool for tool in ("gpg", "wget") if not shutil.which(tool)]
        if missing:
            QMessageBox.warning(
                self,
                "Verification tools required",
                "Install the verification tools with `sudo apt install gnupg wget`, then try again.",
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
        process.start(sys.executable, [str(Path(__file__).with_name("core_download.py"))])

    def _read_core_download_error(self, process):
        self.core_download_stderr += bytes(process.readAllStandardError()).decode("utf-8", "replace")

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
        if sys.platform != "linux":
            self.statusBar().showMessage("Starting a downloaded Core node is available on Linux.")
            return
        default_cookie = default_cookie_path()
        if prefer_existing and default_cookie.is_file():
            self._use_core_connection(default_cookie, 8332)
            self.connect()
            return

        binary = Path(binary) if binary else self._installed_core_binary()
        if not binary or not binary.is_file():
            self._set_core_status("Download and verify Bitcoin Core first", "error")
            self.statusBar().showMessage("Download and verify Bitcoin Core from Welcome, then choose Online Node.")
            return

        data_dir = managed_node_dir()
        cookie = data_dir / ".cookie"
        self._use_core_connection(cookie, MANAGED_RPC_PORT)
        if cookie.is_file():
            self._set_core_status("Connecting to your Bitcoin Core node…")
            self.node_start_timer.start()
            self._poll_managed_node()
            return

        try:
            data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            data_dir.chmod(0o700)
            arguments = [
                f"-datadir={data_dir}",
                "-daemon=0",
                "-server=1",
                f"-prune={PRUNE_TARGET_MIB}",
            ]
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
        self.node_start_timer.start()
        self._poll_managed_node()

    def _poll_managed_node(self):
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
            self._set_core_status("Download and verify Bitcoin Core first", "error")
            self.statusBar().showMessage("Download and verify Core on Welcome before starting cold storage.")
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
        bitcoind = self._installed_core_binary()
        if not bitcoind:
            self._set_core_status("Download and verify Bitcoin Core first", "error")
            self.statusBar().showMessage("Download and verify Core on Welcome before starting cold storage.")
            self.tabs.setCurrentIndex(0)
            return
        session = ColdSystemSession(disable_networking=not self.dev_keep_network)
        self.cold_session = session
        try:
            session.begin()
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
        self.cold_session_id = secrets.token_hex(16)
        self.cold_temp_path = Path("/dev/shm") / f"core-companion-cold-{self.cold_session_id}"
        self.cold_button.setEnabled(False)
        self.cold_button_top.setEnabled(False)
        self.statusBar().showMessage(
            "DEV MODE · host networking on · Core P2P off · swap off"
            if self.dev_keep_network else "Cold session active · networking and swap are off"
        )
        process = QProcess(self)
        self.cold_process = process
        entry = Path(__file__).resolve().parent.parent / "run.py"
        process.setProgram(sys.executable)
        arguments = [
            str(entry), "--cold-helper", "--bitcoind", str(bitcoind.resolve()),
            "--session-id", self.cold_session_id,
        ]
        if self.dev_keep_network:
            arguments.append("--dev-keep-network")
        process.setArguments(arguments)
        process.started.connect(lambda: setattr(self, "cold_process_group", int(process.processId())))
        process.finished.connect(self._cold_helper_finished)
        process.errorOccurred.connect(self._cold_helper_error)
        process.start()

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
            if self.dev_keep_network else "Cold session closed · previous network and swap settings restored"
        )

    def _cold_helper_finished(self, exit_code, exit_status):
        self._restore_cold_system()

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
                self.statusBar().showMessage("Starting the verified Bitcoin Core node…")
                QTimer.singleShot(0, lambda: self._start_managed_node(prefer_existing=False))
                return
            if self.node_start_timer.isActive():
                self._set_core_status("Starting Bitcoin Core…")
                self.statusBar().showMessage("Waiting for Core's local connection…")
                return
            if hasattr(self, "core_status"):
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
        self.address.clear()
        self.receive_qr.clear()
        self.psbt.clear()
        self.receive_label.clear()
        self.receive_done.hide()
        self.receive_used.hide()
        self.generate_button.show()
        self.transactions.setRowCount(0)
        self.recent.setRowCount(0)
        self.addresses.setRowCount(0)
        self.rows = []
        self.skip = 0
        self.page_label.setText("No activity loaded")
        self.network.setText("○  Offline")

    def connect(self):
        if self.busy:
            return
        try:
            cookie_path = self.core_cookie_path or default_cookie_path()
            if not cookie_path.is_file() and sys.platform == "linux" and self._installed_core_binary():
                self._start_managed_node(prefer_existing=False)
                return
            self.connection_fallback = (
                sys.platform == "linux"
                and cookie_path == default_cookie_path()
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
        service = self.service
        self.task(
            "Checking sync progress…",
            lambda: service.rpc.call("getblockchaininfo"),
            self.update_sync_status,
            show_message=False,
        )

    def connected(self, service, data):
        self.connection_fallback = False
        self.node_start_timer.stop()
        if data["chain"].get("chain") != "main":
            self.service = None
            self._clear()
            self.statusBar().showMessage("This wallet view is set up for the expected Bitcoin chain only.")
            return
        self.connection.hide()
        self.service = service
        self._set_core_status("Bitcoin Core connected", "connected")
        self.tabs.setCurrentIndex(1 if self.connection_purpose == "welcome" else 2)
        self.update_sync_status(data["chain"])
        self.sync_timer.start()
        self.wallet_picker.blockSignals(True)
        self.wallet_picker.addItems(data["wallets"])
        self.wallet_picker.blockSignals(False)
        if data["wallets"]:
            self.refresh()
        else:
            self.online_name.setText("No watch-only wallet loaded")
            self.sync_label.setText("Core is connected")
            self.statusBar().showMessage(
                "No watch-only wallet is loaded. Restore the cold signer’s export in Core, then reconnect."
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
        self.address.clear()
        self.skip = 0
        self.transactions.setRowCount(0)
        self.addresses.setRowCount(0)
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
        info, chain = data["info"], data["chain"]
        self.online_name.setText(f"{info['walletname']} (watch-only)")
        self.update_sync_status(chain)
        self.rows = list(reversed(data["transactions"]))
        self.transactions.setRowCount(len(self.rows))
        self.recent.setRowCount(min(4, len(self.rows)))
        for row, tx in enumerate(self.rows):
            confirmations = tx.get("confirmations", 0)
            status = "Conflicted" if confirmations < 0 else ("Abandoned" if tx.get("abandoned") else ("Unconfirmed" if confirmations == 0 else f"✓  {confirmations} confirmed"))
            amount = tx.get("amount", 0)
            values = [status, datetime.fromtimestamp(tx.get("time", 0)).strftime("%d %b %Y · %H:%M"), tx.get("label") or tx.get("category", ""), ("+" if amount > 0 else "") + btc(amount)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(tx.get("txid", ""))
                if column == 0:
                    item.setForeground(QColor("#a97919" if confirmations == 0 else ("#b54c4c" if confirmations < 0 else "#427e68")))
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(QFont("Consolas", 11))
                    if amount > 0:
                        item.setForeground(QColor("#2c8265"))
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
                        recent_item.setFont(QFont("Consolas", 10))
                    self.recent.setItem(row, column, recent_item)
        self.address_rows = data["addresses"]
        self.addresses.setRowCount(len(self.address_rows))
        for row, address in enumerate(self.address_rows):
            for column, value in enumerate([address.get("label", ""), address["address"], btc(address.get("amount", 0))]):
                item = QTableWidgetItem(value)
                if column in (1, 2):
                    item.setFont(QFont("Consolas", 10))
                self.addresses.setItem(row, column, item)
        self.page_label.setText(f"{len(self.rows)} entries  ·  page {self.skip // 100 + 1}")
        self.filter_history()
        self.network.setText(f"●  Bitcoin Core · block {chain['blocks']:,}")
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

    def paginate(self, delta):
        if not self.busy and self.service:
            self.skip = max(0, self.skip + delta)
            self.refresh()

    def generate(self):
        if not self.service or not self.wallet_picker.currentText():
            self.statusBar().showMessage("Connect and select a wallet first.")
            return
        service, name, text = self.service, self.wallet_picker.currentText(), self.receive_label.text()
        self.task("Requesting an address from Core…", lambda: service.receive(name, text), self.received)

    def _open_receive(self):
        self.address.clear()
        self.receive_qr.clear()
        self.receive_label.clear()
        self.receive_used.hide()
        self.receive_done.hide()
        self.generate_button.show()
        self.tabs.setCurrentIndex(4)

    def received(self, result):
        self.address.setText(result[0])
        self.receive_qr.setPixmap(self._qr_pixmap(result[0], size=190))
        self.receive_used.show()
        self.receive_done.show()
        self.generate_button.hide()
        self.statusBar().showMessage("Address generated by Core. Verify independently before use.")

    @staticmethod
    def _qr_pixmap(payload, size=190):
        code = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=4)
        code.add_data(payload)
        code.make(fit=True)
        matrix = code.get_matrix()
        image = QImage(len(matrix), len(matrix), QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#142331"))
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    painter.drawRect(QRect(x, y, 1, 1))
        painter.end()
        return QPixmap.fromImage(image).scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
        )

    def copy_address(self):
        address = self.address.text()
        if not address:
            self.statusBar().showMessage("Generate an address first.")
            return
        QApplication.clipboard().setText(address)
        self.statusBar().showMessage("Address copied. Verify the complete pasted address before use.")

    def inspect(self):
        if not self.service or not self.wallet_picker.currentText():
            self.statusBar().showMessage("Connect and select a wallet first.")
            return
        text = self.psbt.toPlainText().strip()
        if not text or len(text) > 2 * 1024 * 1024:
            self.statusBar().showMessage("Enter a base64 PSBT smaller than 2 MiB.")
            return
        service, name = self.service, self.wallet_picker.currentText()
        self.task("Inspecting PSBT…", lambda: service.inspect_psbt(name, text), lambda result: self.show_text("Core PSBT inspection · no signing", json.dumps(result, indent=2, default=str)))

    def transaction_details(self, row, column):
        self.show_text("Wallet activity entry", json.dumps(self.rows[row], indent=2, default=str))

    def address_details(self, row, column):
        self.show_text("Receiving address", json.dumps(self.address_rows[row], indent=2, default=str))

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
        self.show_text("About Core Companion", "Core Companion · early development build\n\nThe online view uses a local Bitcoin Core node. Companion can start the verified node or connect to a running local node.\n\nCold signing uses a separate short-lived Core process on Linux. It supports BIP39 create/recovery, BIP87 multisig setup, and Core-backed PSBT review and signing. It does not finalize or broadcast.\n\nPython / Qt Widgets. No browser engine or local web server.")

    def closeEvent(self, event):
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
            event.accept()
            return
        answer = QMessageBox.warning(
            self,
            "Cold signer is active",
            "Closing the main app will close the cold signer and stop its temporary Core process. "
            + ("Swap will be restored; host networking was left on."
               if self.dev_keep_network else "Networking and swap will be restored after those processes stop."),
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

def main(argv=None):
    parser = argparse.ArgumentParser(description="Bitcoin Core wallet companion")
    parser.add_argument("--cold-helper", action="store_true")
    parser.add_argument("--bitcoind")
    parser.add_argument("--session-id")
    parser.add_argument(
        "--dev-keep-network", action="store_true",
        help="development only: leave host networking enabled during cold signer sessions",
    )
    args = parser.parse_args(argv)
    application = QApplication([])
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
        application.exec()
        return
    window = App(dev_keep_network=args.dev_keep_network)
    window.show()
    if default_cookie_path().is_file():
        window._use_core_connection(default_cookie_path(), 8332)
        QTimer.singleShot(0, window.connect)
    elif sys.platform == "linux" and (managed_node_dir() / ".cookie").is_file():
        window._use_core_connection(managed_node_dir() / ".cookie", MANAGED_RPC_PORT)
        QTimer.singleShot(0, window.connect)
    elif sys.platform == "linux" and window._installed_core_binary():
        window._set_core_status("Bitcoin Core is ready. Choose Online Node to start syncing.")
    else:
        window._set_core_status("Bitcoin Core not found. Start it or download it below.", "error")
    application.exec()
