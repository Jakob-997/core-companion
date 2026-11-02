"""Short-lived Linux UI for creating or recovering a Core signing wallet."""

import base64
import json
import secrets
import unicodedata
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .qr import qr_pixmap
from .scanner import QRScanner
from qrcode.exceptions import DataOverflowError
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QPlainTextEdit,
    QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QToolTip, QSizePolicy,
)

from .linux_cold import ColdSetupError
from .offline_core import OfflineCore
from .rpc import CoreError
from .wallet import validate_wallet_name
from .seed import (
    SeedError,
    entropy_from_sources,
    final_word_candidates,
    phrase_from_entropy,
    validate_phrase,
)
from .theme import stylesheet
from .widgets import ActionRow, ChoiceRow, IconButton, LineIcon, fixed_font


def _label(text, muted=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if muted:
        widget.setObjectName("Muted")
    return widget


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


class ColdSignerDialog(QDialog):
    def __init__(self, bitcoind, session_id, parent=None, *, dev_keep_network=False):
        super().__init__(parent)
        self.setObjectName("ColdSigner")
        self.setWindowTitle("Core Companion — Cold storage")
        self.resize(1280, 850)
        self.setMinimumSize(980, 680)
        self.dark_mode = False
        self.setStyleSheet(stylesheet())
        self.core = None
        self.wallet_digest = None
        self.os_entropy = None
        self.phrase = None
        self.words = []
        self.challenge = []
        self.wallet_mode = "single"
        self.setup_choice = None
        self.type_choice = None
        self.phrase_source = "create"
        self.current_bip39_passphrase = ""
        self.current_wallet_passphrase = ""
        self.recovery_prefix = None
        self.session_id = session_id
        self.dev_keep_network = bool(dev_keep_network)
        self.wallet_encrypted = False
        self.wallet_ready = False
        self.multisig_prepared = False
        self.reviewed_psbt = None
        self.reviewed_id = None
        self.scanner = None
        self.scanner_target_field = None
        self.help_mode = False
        self.wallet_display_name = "Cold storage"
        self.wallet_fingerprint = ""
        self.address_records = []
        self.active_address = None
        self.help_targets = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 10)
        root.setSpacing(9)
        header = QHBoxLayout()
        mark = LineIcon("bitcoin", "Mark", stroke_width=1.9, inset=4)
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(mark)
        brand = _label("Core Companion", False)
        brand.setObjectName("Brand")
        header.addWidget(brand)
        header.addStretch()
        self.help_button = IconButton(
            "i", "Help", self._toggle_help_mode,
            tooltip="Turn on instant explanations. Hover over a control to see what it does.",
        )
        header.addWidget(self.help_button)
        self.theme_button = IconButton("dark", "Dark mode", self._toggle_theme)
        header.addWidget(self.theme_button)
        root.addLayout(header)
        divider = QFrame()
        divider.setObjectName("HeaderDivider")
        divider.setFixedHeight(1)
        root.addWidget(divider)
        self.stack = QStackedWidget()
        if self.dev_keep_network:
            notice = _label(
                "DEVELOPMENT MODE · Host networking stays on. Core peer networking stays off. Use test wallets only.",
                False,
            )
            notice.setObjectName("DevNotice")
            root.addWidget(notice)
        root.addWidget(self.stack, 1)
        self._build_start_page()
        self._build_entropy_page()
        self._build_recovery_page()
        self._build_phrase_page()
        self._build_confirm_page()
        self._build_multisig_page()
        self._build_complete_page()
        self._build_psbt_page()
        self._build_verify_address_page()
        self._build_scan_page()
        self._build_addresses_page()
        self._build_address_detail_page()
        self._build_tools_page()
        self._build_policy_page()
        self._build_settings_page()
        self._build_setup_page()
        self._build_type_page()
        self._build_protection_page()
        self.status_left = _label("Cold signer · offline", True)
        self.status_right = _label("Setup", True)
        self.status_left.setWordWrap(False)
        self.status_right.setWordWrap(False)
        status = QHBoxLayout()
        status.addWidget(self.status_left)
        status.addStretch()
        status.addWidget(self.status_right)
        root.addLayout(status)
        self._install_help_targets()
        self.stack.setCurrentIndex(15)
        self._open_core(bitcoind)

    def _card(self, *, scroll=False):
        page = QWidget()
        page.setObjectName("Page")
        shell = QVBoxLayout(page)
        shell.setContentsMargins(30, 0, 30, 0)
        card = QWidget()
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        shell.addWidget(card, 1)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        if scroll:
            viewport = QScrollArea()
            viewport.setWidgetResizable(True)
            viewport.setFrameShape(QFrame.Shape.NoFrame)
            viewport.setWidget(page)
            self.stack.addWidget(viewport)
        else:
            self.stack.addWidget(page)
        return layout

    def _page(self):
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 16, 30, 16)
        layout.setSpacing(14)
        self.stack.addWidget(page)
        return layout

    def _build_start_page(self):
        layout = self._card()
        title = _label("Wallet details", False)
        title.setObjectName("Title")
        layout.addWidget(title)
        self.wallet_name_input = QLineEdit()
        self.wallet_name_input.setPlaceholderText("Wallet name")
        layout.addWidget(self.wallet_name_input)
        form = QFormLayout()
        self.address_type_form = form
        self.address_type = QComboBox()
        for title, code in (
            ("Native SegWit", "bech32"),
            ("Taproot", "bech32m"),
            ("Nested SegWit", "p2sh-segwit"),
            ("Legacy", "legacy"),
        ):
            self.address_type.addItem(title, code)
        form.addRow("Address type", self.address_type)
        layout.addLayout(form)

        footer = QHBoxLayout()
        back = QPushButton("‹  Back")
        back.setObjectName("Quiet")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(16))
        footer.addWidget(back)
        footer.addStretch()
        continue_button = QPushButton("Continue  →")
        continue_button.setObjectName("Primary")
        continue_button.clicked.connect(self._continue_wallet_setup)
        footer.addWidget(continue_button)
        layout.addLayout(footer)

    def _build_entropy_page(self):
        layout = self._card()
        title = _label("Recovery phrase setup", False)
        title.setObjectName("Title")
        layout.addWidget(title)
        self.audit_details = QWidget()
        audit_layout = QVBoxLayout(self.audit_details)
        audit_layout.setContentsMargins(0, 0, 0, 0)
        audit_layout.setSpacing(10)
        form = QFormLayout()
        self.dice = QLineEdit()
        self.dice.setPlaceholderText("Optional · enter rolls from 1 to 6")
        form.addRow("Dice rolls", self.dice)
        self.dice_count = _label("0 rolls entered", True)
        self.dice.textChanged.connect(lambda text: self.dice_count.setText(
            f"{sum(face in '123456' for face in text)} rolls entered"
        ))
        form.addRow("", self.dice_count)
        self.word_count = QComboBox()
        for count in (12, 15, 18, 21, 24):
            self.word_count.addItem(f"{count} words", count)
        form.addRow("Recovery phrase", self.word_count)
        layout.addLayout(form)
        audit_layout.addWidget(_label("Secret · verify on an offline computer only.", True))
        self.entropy_audit = QPlainTextEdit()
        self.entropy_audit.setReadOnly(True)
        self.entropy_audit.setMaximumHeight(250)
        audit_layout.addWidget(self.entropy_audit)
        self.audit_toggle = QPushButton("▸ Audit details")
        self.audit_toggle.setCheckable(True)
        self.audit_toggle.setToolTip("Show the hashes, secret calculation and reproduction command.")
        self.audit_toggle.toggled.connect(self.audit_details.setVisible)
        self.audit_toggle.toggled.connect(lambda expanded: self.audit_toggle.setText(
            "▾ Audit details" if expanded else "▸ Audit details"
        ))
        layout.addWidget(self.audit_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.audit_details)
        self.audit_details.hide()
        self.dice.textChanged.connect(self._update_entropy_audit)
        self.word_count.currentIndexChanged.connect(self._update_entropy_audit)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        footer.addWidget(back)
        footer.addStretch()
        generate = QPushButton("Generate recovery phrase")
        generate.setObjectName("Primary")
        generate.clicked.connect(self._generate_phrase)
        footer.addWidget(generate)
        layout.addLayout(footer)

    def _build_recovery_page(self):
        layout = self._card()
        title = _label("Recover from a BIP39 phrase", False)
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(_label(
            "Enter the full phrase, or leave the final word blank. The checksum can allow more than one final word; "
            "choose the one written on your backup.", True
        ))
        self.recovery_count = QComboBox()
        for count in (12, 15, 18, 21, 24):
            self.recovery_count.addItem(f"{count} words", count)
        layout.addWidget(self.recovery_count)
        self.recovery_text = QPlainTextEdit()
        self.recovery_text.setPlaceholderText("Enter the words in order, separated by spaces")
        self.recovery_text.setMaximumHeight(135)
        layout.addWidget(self.recovery_text)
        self.recovery_text.textChanged.connect(self._clear_recovery_candidates)
        self.recovery_hint = _label("", True)
        layout.addWidget(self.recovery_hint)
        self.final_word = QComboBox()
        self.final_word.hide()
        layout.addWidget(self.final_word)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        footer.addWidget(back)
        footer.addStretch()
        continue_button = QPushButton("Continue")
        continue_button.setObjectName("Primary")
        continue_button.clicked.connect(self._continue_recovery)
        footer.addWidget(continue_button)
        layout.addLayout(footer)

    def _build_phrase_page(self):
        layout = self._card()
        title = _label("Write down your recovery phrase", False)
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(_label("Write every word in order. You’ll type the full phrase next.", True))
        self.word_grid = QGridLayout()
        self.word_grid.setHorizontalSpacing(48)
        self.word_grid.setVerticalSpacing(10)
        self.word_labels = []
        words_panel = QWidget()
        words_panel.setLayout(self.word_grid)
        words_panel.setMaximumWidth(680)
        layout.addWidget(words_panel, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        footer.addWidget(back)
        footer.addStretch()
        self._add_confirmation_skip(footer)
        next_button = QPushButton("I wrote it down")
        next_button.setObjectName("Primary")
        next_button.clicked.connect(self._show_confirmation)
        footer.addWidget(next_button)
        layout.addLayout(footer)

    def _build_confirm_page(self):
        layout = self._card()
        title = _label("Confirm your phrase", False)
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(_label("Type every word from your backup in order.", True))
        self.challenge_form = QGridLayout()
        self.challenge_fields = []
        layout.addLayout(self.challenge_form)
        layout.addStretch()
        footer = QHBoxLayout()
        self.confirm_back = QPushButton("Back")
        self.confirm_back.clicked.connect(self._back_from_confirmation)
        footer.addWidget(self.confirm_back)
        footer.addStretch()
        self._add_confirmation_skip(footer)
        continue_button = QPushButton("Continue")
        continue_button.setObjectName("Primary")
        continue_button.clicked.connect(self._confirm_phrase)
        footer.addWidget(continue_button)
        layout.addLayout(footer)

    def _add_confirmation_skip(self, footer):
        if self.dev_keep_network:
            skip = QPushButton("Skip confirmation (testing)")
            skip.clicked.connect(self._skip_confirmation)
            footer.addWidget(skip)

    def _skip_confirmation(self):
        if self.dev_keep_network and self.phrase:
            self._show_protection()

    def _build_multisig_page(self):
        card = QWidget()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(card)
        self.stack.addWidget(scroll)
        title = _label("Multisig setup", False)
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(_label(
            "Share your public signer key, then add the other signers’ BIP87 keys.", True
        ))
        own_key_row = QHBoxLayout()
        self.multisig_key_qr = QLabel()
        self.multisig_key_qr.setObjectName("QR")
        self.multisig_key_qr.setFixedSize(260, 260)
        self.multisig_key_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        own_key_row.addWidget(self.multisig_key_qr)
        own_key_fields = QVBoxLayout()
        own_key_fields.addWidget(_label("Your public signer key"))
        self.multisig_own_key = QPlainTextEdit()
        self.multisig_own_key.setReadOnly(True)
        self.multisig_own_key.setMaximumHeight(110)
        self.multisig_own_key.setToolTip("Share this public BIP87 key with the other signers. It contains no private key.")
        own_key_fields.addWidget(self.multisig_own_key)
        own_key_fields.addStretch()
        own_key_row.addLayout(own_key_fields, 1)
        layout.addLayout(own_key_row)
        self.threshold = QSpinBox()
        self.threshold.setMinimum(1)
        self.threshold.setMaximum(3)
        self.threshold.setValue(2)
        self.signer_count_label = _label("3 signers total", True)
        self.own_signer_name = QLineEdit("This signer")
        form = QFormLayout()
        form.addRow("This signer", self.own_signer_name)
        form.addRow("Required signatures", self.threshold)
        form.addRow("Signers", self.signer_count_label)
        layout.addLayout(form)
        self.signer_grid = QGridLayout()
        self.signer_grid.setColumnStretch(2, 1)
        layout.addLayout(self.signer_grid)
        self.signer_fields = []
        for index in range(2):
            self._add_signer_fields(f"Signer {index + 2}")
        signer_buttons = QHBoxLayout()
        add_signer = QPushButton("+ Add signer")
        add_signer.clicked.connect(self._add_signer)
        signer_buttons.addWidget(add_signer)
        remove_signer = QPushButton("− Remove last")
        remove_signer.clicked.connect(self._remove_signer)
        signer_buttons.addWidget(remove_signer)
        signer_buttons.addStretch()
        layout.addLayout(signer_buttons)
        self.multisig_password = QLineEdit()
        self.multisig_password.setPlaceholderText("Wallet password to finish setup")
        self.multisig_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.multisig_password.setToolTip("Unlock the encrypted wallet briefly to import the completed multisig policy.")
        self.multisig_password.hide()
        layout.addWidget(self.multisig_password)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(self._finish)
        footer.addWidget(back)
        footer.addStretch()
        continue_button = QPushButton("Continue")
        continue_button.setObjectName("Primary")
        continue_button.clicked.connect(self._create_multisig)
        footer.addWidget(continue_button)
        layout.addLayout(footer)

    def _build_complete_page(self):
        layout = self._page()
        identity = QFrame()
        identity.setObjectName("IdentityPanel")
        identity_row = QHBoxLayout(identity)
        identity_row.setContentsMargins(20, 18, 18, 18)
        identity_row.setSpacing(18)
        self.identity_mark = QWidget()
        self.identity_mark.setObjectName("IdentityMark")
        self.identity_mark.setFixedSize(60, 60)
        self.identity_grid = QGridLayout(self.identity_mark)
        self.identity_grid.setContentsMargins(5, 5, 5, 5)
        self.identity_grid.setSpacing(2)
        self.identity_tiles = []
        for index in range(25):
            tile = QLabel()
            tile.setObjectName("IdentityTile")
            self.identity_grid.addWidget(tile, index // 5, index % 5)
            self.identity_tiles.append(tile)
        identity_row.addWidget(self.identity_mark)
        identity_copy = QVBoxLayout()
        identity_copy.setSpacing(5)
        identity_title = QHBoxLayout()
        identity_title.setSpacing(9)
        self.identity_name = _label("Cold storage", False)
        self.identity_name.setObjectName("IdentityName")
        identity_title.addWidget(self.identity_name)
        self.identity_badge = QLabel("Cold signer")
        self.identity_badge.setObjectName("ColdBadge")
        identity_title.addWidget(self.identity_badge)
        identity_title.addStretch(1)
        identity_copy.addLayout(identity_title)
        identity_meta = QHBoxLayout()
        identity_meta.setSpacing(18)
        self.identity_policy = _label("Single-signature", True)
        self.identity_policy.setObjectName("IdentityMeta")
        self.identity_fingerprint = _label("Signer · unavailable", True)
        self.identity_fingerprint.setObjectName("IdentityMeta")
        identity_meta.addWidget(self.identity_policy)
        identity_meta.addWidget(self.identity_fingerprint)
        identity_meta.addStretch(1)
        identity_copy.addLayout(identity_meta)
        identity_row.addLayout(identity_copy, 1)
        change = QPushButton("↔")
        change.setObjectName("Quiet")
        change.setToolTip("Close this temporary signer session before opening another wallet.")
        change.clicked.connect(self._change_wallet)
        identity_row.addWidget(change, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(identity)

        heading = _label("Choose an action", False)
        heading.setObjectName("Title")
        layout.addWidget(heading)
        actions = QVBoxLayout()
        actions.setSpacing(9)
        scan = ActionRow(
            "▦", "Scan QR", "", primary=True,
            tooltip="Verify a receive address or review a PSBT before signing.",
        )
        scan.clicked.connect(lambda: self.stack.setCurrentIndex(9))
        addresses = ActionRow(
            "▣", "View wallet addresses", "",
            tooltip="See saved addresses and labels generated or confirmed by this signer.",
        )
        addresses.clicked.connect(self._open_addresses)
        tools = ActionRow(
            "⚙", "Tools & Settings", "",
            tooltip="Export the watch-only wallet, view the policy, or change settings.",
        )
        tools.clicked.connect(lambda: self.stack.setCurrentIndex(12))
        actions.addWidget(scan)
        actions.addWidget(addresses)
        actions.addWidget(tools)
        layout.addLayout(actions)
        layout.addStretch(1)

    def _build_scan_page(self):
        layout = self._card()
        self._add_back_heading(layout, "Scan QR code", "", 6)
        self.scan_target = QFrame()
        self.scan_target.setObjectName("ScanTarget")
        self.scan_target.setMinimumHeight(190)
        scan_layout = QVBoxLayout(self.scan_target)
        scan_layout.setContentsMargins(20, 18, 20, 18)
        scan_layout.setSpacing(7)
        scan_icon = LineIcon("▦", "ScanGlyph", stroke_width=1.7, inset=0)
        scan_icon.setFixedSize(38, 38)
        scan_layout.addWidget(scan_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        scan_layout.addWidget(_label("Ready to scan", False), 0, Qt.AlignmentFlag.AlignHCenter)
        scan_hint = _label("Point the camera at a wallet QR code.", True)
        scan_layout.addWidget(scan_hint, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.scan_target)
        self.scan_payload = QLineEdit()
        self.scan_payload.setPlaceholderText("Scanned QR data appears here")
        self.scan_payload.returnPressed.connect(self._process_scanned_payload)
        layout.addWidget(self.scan_payload)
        controls = QHBoxLayout()
        start = QPushButton("Start camera scan")
        start.setObjectName("Primary")
        start.clicked.connect(lambda: self._start_qr_scanner(self.scan_payload))
        controls.addWidget(start)
        check = QPushButton("Continue")
        check.clicked.connect(self._process_scanned_payload)
        controls.addWidget(check)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addStretch()

    def _build_addresses_page(self):
        layout = self._card()
        header = QHBoxLayout()
        title = _label("Wallet addresses", False)
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch()
        generate = QPushButton("Generate address")
        generate.setObjectName("Primary")
        generate.clicked.connect(self._generate_receive_address)
        header.addWidget(generate)
        layout.addLayout(header)
        layout.addWidget(_label("Addresses generated or confirmed on this signer.", True))
        self.address_table = QTableWidget(0, 3)
        self.address_table.setHorizontalHeaderLabels(["LABEL", "ADDRESS", "SAVED"])
        self.address_table.verticalHeader().hide()
        self.address_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.address_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.address_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.address_table.setShowGrid(False)
        self.address_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.address_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.address_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.address_table.cellDoubleClicked.connect(self._open_address_from_row)
        layout.addWidget(self.address_table, 1)
        layout.addWidget(_label("Double-click an address to view its QR code or edit its label.", True))
        self._add_back_button(layout, 6, "Back to wallet")

    def _build_address_detail_page(self):
        layout = self._card()
        self.address_detail_title = _label("Wallet address", False)
        self.address_detail_title.setObjectName("Title")
        back = QPushButton("‹  Back to addresses")
        back.setObjectName("Quiet")
        back.clicked.connect(self._open_addresses)
        layout.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.address_detail_title)
        detail = QHBoxLayout()
        self.address_qr = QLabel()
        self.address_qr.setObjectName("QR")
        self.address_qr.setFixedSize(320, 320)
        self.address_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail.addWidget(self.address_qr, 0, Qt.AlignmentFlag.AlignTop)
        fields = QVBoxLayout()
        fields.addWidget(_label("ADDRESS", False))
        self.address_detail_value = QLineEdit()
        self.address_detail_value.setReadOnly(True)
        self.address_detail_value.setFont(fixed_font(9))
        fields.addWidget(self.address_detail_value)
        fields.addWidget(_label("LABEL · OPTIONAL", False))
        self.address_detail_label = QLineEdit()
        self.address_detail_label.setPlaceholderText("e.g. Long-term savings")
        fields.addWidget(self.address_detail_label)
        self.address_used_status = _label("✓  Used on this signer", True)
        fields.addWidget(self.address_used_status)
        fields.addStretch()
        detail.addLayout(fields, 1)
        layout.addLayout(detail)
        done = QPushButton("Done")
        done.setObjectName("Primary")
        done.clicked.connect(self._save_address_detail)
        layout.addWidget(done, 0, Qt.AlignmentFlag.AlignRight)
        layout.addStretch()

    def _build_tools_page(self):
        layout = self._card()
        self._add_back_heading(layout, "Tools & Settings", "Wallet policy, exports, and preferences.", 6)
        actions = QVBoxLayout()
        actions.setSpacing(9)
        policy = ActionRow("⌘", "Wallet policy", "", tooltip="Review the wallet identity, signer keys, and public descriptors.")
        policy.clicked.connect(lambda: self.stack.setCurrentIndex(13))
        export = ActionRow(
            "⇧", "Export watch-only wallet", "",
            tooltip="Export public wallet data for use on the online node.", icon_key="export",
        )
        export.clicked.connect(self._export_watchonly_wallet)
        settings = ActionRow("⚙", "Settings", "", tooltip="Change appearance and view cold-signer session details.")
        settings.clicked.connect(lambda: self.stack.setCurrentIndex(14))
        for action in (policy, export, settings):
            actions.addWidget(action)
        layout.addLayout(actions)
        layout.addStretch()

    def _build_policy_page(self):
        layout = self._card()
        self._add_back_heading(layout, "Wallet policy", "Public wallet data supplied and checked by Bitcoin Core.", 12)
        self.policy_identity = _label("")
        layout.addWidget(self.policy_identity)
        self.signer_map = _label("")
        self.signer_map.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.signer_map)
        layout.addWidget(_label("PUBLIC DESCRIPTORS", False))
        self.descriptors = QPlainTextEdit()
        self.descriptors.setReadOnly(True)
        self.descriptors.setMaximumHeight(250)
        layout.addWidget(self.descriptors, 1)

    def _build_settings_page(self):
        layout = self._card()
        self._add_back_heading(layout, "Settings", "", 12)
        appearance = QHBoxLayout()
        appearance.addWidget(_label("Appearance", False))
        appearance.addStretch()
        self.settings_theme_button = IconButton("dark", "Dark mode", self._toggle_theme)
        appearance.addWidget(self.settings_theme_button)
        layout.addLayout(appearance)
        layout.addWidget(_label("Cold signer session", False))
        self.session_details = _label("Networking and swap are disabled for this session.", True)
        layout.addWidget(self.session_details)
        layout.addWidget(_label("The signing wallet is held in RAM by Bitcoin Core. Closing the session stops Core and removes its temporary wallet files.", True))
        layout.addStretch()

    def _build_setup_page(self):
        layout = self._page()
        heading = _label("Wallet setup", False)
        heading.setObjectName("Title")
        layout.addWidget(heading)
        choices = QVBoxLayout()
        choices.setSpacing(0)
        self.create_choice = ChoiceRow("＋", "Create a new wallet", accent="blue")
        self.create_choice.clicked.connect(lambda: self._choose_setup("new"))
        self.recover_choice = ChoiceRow("↻", "Use an existing wallet", accent="blue")
        self.recover_choice.clicked.connect(lambda: self._choose_setup("recover"))
        choices.addWidget(self.create_choice)
        choices.addLayout(self._or_separator())
        choices.addWidget(self.recover_choice)
        layout.addLayout(choices)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("‹  Back")
        back.setObjectName("Quiet")
        back.clicked.connect(self._finish)
        footer.addWidget(back)
        footer.addStretch()
        self.setup_continue = QPushButton("Continue  →")
        self.setup_continue.setObjectName("Primary")
        self.setup_continue.setEnabled(False)
        self.setup_continue.clicked.connect(lambda: self.stack.setCurrentIndex(16))
        footer.addWidget(self.setup_continue)
        layout.addLayout(footer)

    def _build_type_page(self):
        layout = self._page()
        heading = _label("Choose wallet type", False)
        heading.setObjectName("Title")
        layout.addWidget(heading)
        choices = QVBoxLayout()
        choices.setSpacing(0)
        self.single_choice = ChoiceRow(
            "◉", "Single-signature", "One key creates and signs for this wallet.", accent="blue"
        )
        self.single_choice.clicked.connect(lambda: self._choose_type("single"))
        self.multi_choice = ChoiceRow(
            "⌘", "Multisig · BIP87", "Several signers share the wallet; choose the required threshold.", accent="blue"
        )
        self.multi_choice.clicked.connect(lambda: self._choose_type("multisig"))
        choices.addWidget(self.single_choice)
        choices.addLayout(self._or_separator())
        choices.addWidget(self.multi_choice)
        layout.addLayout(choices)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("‹  Back")
        back.setObjectName("Quiet")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(15))
        footer.addWidget(back)
        footer.addStretch()
        self.type_continue = QPushButton("Continue  →")
        self.type_continue.setObjectName("Primary")
        self.type_continue.setEnabled(False)
        self.type_continue.clicked.connect(self._continue_type_choice)
        footer.addWidget(self.type_continue)
        layout.addLayout(footer)

    @staticmethod
    def _or_separator():
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
        divider.addWidget(_label("OR", True))
        divider.addWidget(right_rule, 1)
        return divider

    def _build_protection_page(self):
        layout = self._card()
        heading = _label("Wallet protection", False)
        heading.setObjectName("Title")
        layout.addWidget(heading)
        protection = QGroupBox("Optional protection")
        content = QVBoxLayout(protection)
        content.setSpacing(8)
        self.use_bip39_passphrase = QCheckBox("Use a BIP39 passphrase")
        self.use_bip39_passphrase.setToolTip("An additional secret that creates a different wallet from the same recovery phrase.")
        content.addWidget(self.use_bip39_passphrase)
        self.bip39_passphrase1 = QLineEdit()
        self.bip39_passphrase1.setPlaceholderText("BIP39 passphrase")
        self.bip39_passphrase1.setEchoMode(QLineEdit.EchoMode.Password)
        self.bip39_passphrase2 = QLineEdit()
        self.bip39_passphrase2.setPlaceholderText("Confirm BIP39 passphrase")
        self.bip39_passphrase2.setEchoMode(QLineEdit.EchoMode.Password)
        self.bip39_show = QCheckBox("Show BIP39 passphrase")
        content.addWidget(self.bip39_passphrase1)
        content.addWidget(self.bip39_passphrase2)
        content.addWidget(self.bip39_show)
        self.use_bip39_passphrase.toggled.connect(self._toggle_bip39_fields)
        self.bip39_show.toggled.connect(self._toggle_bip39_visibility)
        self._toggle_bip39_fields(False)

        self.encrypt_wallet = QCheckBox("Encrypt wallet")
        self.encrypt_wallet.setToolTip("Encrypt the temporary Bitcoin Core wallet file for this session.")
        content.addWidget(self.encrypt_wallet)
        self.wallet_password1 = QLineEdit()
        self.wallet_password1.setPlaceholderText("Password")
        self.wallet_password1.setEchoMode(QLineEdit.EchoMode.Password)
        self.wallet_password2 = QLineEdit()
        self.wallet_password2.setPlaceholderText("Confirm password")
        self.wallet_password2.setEchoMode(QLineEdit.EchoMode.Password)
        self.wallet_show = QCheckBox("Show password")
        content.addWidget(self.wallet_password1)
        content.addWidget(self.wallet_password2)
        content.addWidget(self.wallet_show)
        self.encrypt_wallet.toggled.connect(self._toggle_wallet_fields)
        self.wallet_show.toggled.connect(self._toggle_wallet_visibility)
        self._toggle_wallet_fields(False)
        layout.addWidget(protection)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("‹  Back")
        back.setObjectName("Quiet")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(2 if self.phrase_source == "recover" else 4))
        footer.addWidget(back)
        footer.addStretch()
        proceed = QPushButton("Continue")
        proceed.setObjectName("Primary")
        proceed.clicked.connect(self._finish_wallet_protection)
        footer.addWidget(proceed)
        layout.addLayout(footer)

    def _choose_setup(self, choice):
        self._reset_protection()
        if choice != self.setup_choice:
            self.wallet_digest = self.os_entropy = self.phrase = None
            self.entropy_audit.clear()
            self.words.clear()
            self.dice.clear()
        self.setup_choice = choice
        self.create_choice.setChecked(choice == "new")
        self.recover_choice.setChecked(choice == "recover")
        self.setup_continue.setEnabled(True)

    def _choose_type(self, choice):
        self.type_choice = choice
        self.single_choice.setChecked(choice == "single")
        self.multi_choice.setChecked(choice == "multisig")
        self.type_continue.setEnabled(True)

    def _continue_type_choice(self):
        if self.type_choice is None:
            return
        self.wallet_mode = self.type_choice
        self.address_type.setVisible(self.type_choice == "single")
        address_label = self.address_type_form.labelForField(self.address_type)
        if address_label:
            address_label.setVisible(self.type_choice == "single")
        self.stack.setCurrentIndex(0)

    def _continue_wallet_setup(self):
        try:
            validate_wallet_name(self.wallet_name_input.text().strip())
        except CoreError as exc:
            QMessageBox.warning(self, "Wallet name", str(exc))
            self.wallet_name_input.setFocus()
            return
        if self.setup_choice == "new":
            self._start_new_wallet()
        elif self.setup_choice == "recover":
            self._start_recovery()

    def _finish_wallet_protection(self):
        if not self._read_protection_options():
            return
        if self.wallet_mode == "multisig":
            self._prepare_multisig()
        else:
            self._create_single_signature()

    def _add_back_button(self, layout, target, text):
        back = QPushButton("‹  " + text)
        back.setObjectName("Quiet")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(target))
        layout.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)

    def _add_back_heading(self, layout, title, description, target):
        self._add_back_button(layout, target, "Back")
        heading = _label(title, False)
        heading.setObjectName("Title")
        layout.addWidget(heading)
        if description:
            layout.addWidget(_label(description, True))

    def _install_help_targets(self):
        fields = {
            self.wallet_name_input: "A name for this wallet in the interface and public backup. It does not change the keys.",
            self.address_type: "Choose the address format. Keep this choice with your recovery backup to recreate the same wallet.",
            self.dice: "Optional: enter dice faces from 1 to 6 in order. They are mixed with the computer randomness and wallet-file hash.",
            self.word_count: "Choose the length of the new recovery phrase. Write down every word in order.",
            self.entropy_audit: "Secret source values, the exact SHA-256 command, and the resulting entropy. These values can recreate your recovery phrase.",
            self.recovery_count: "Choose the number of words on your existing recovery backup.",
            self.recovery_text: "Enter your existing recovery words in order. This offline signer checks their BIP39 checksum.",
            self.final_word: "Choose the final word from your backup. Several words can pass the checksum; only your original word restores the intended wallet.",
            self.threshold: "The number of different signers required to authorize a transaction.",
            self.own_signer_name: "A short label for this device or signer, so you can distinguish it from the other signers.",
            self.address_detail_value: "The complete receiving address generated or checked by Bitcoin Core. Compare every character when verifying it elsewhere.",
            self.address_detail_label: "An optional note for this address. It is kept only for the current cold session.",
            self.descriptors: "Public receive and change descriptors checked by Core. Multisig recovery needs this policy as well as the required private keys.",
            self.bip39_passphrase1: "An extra secret used with the recovery phrase. A different passphrase produces a different wallet; there is no wrong-passphrase warning.",
            self.bip39_passphrase2: "Enter the BIP39 passphrase again to check for typing mistakes.",
            self.wallet_password1: "Encrypt the temporary Core wallet file with a password of at least 10 characters. This is separate from a BIP39 passphrase.",
            self.wallet_password2: "Enter the wallet-file password again to check for typing mistakes.",
            self.scan_payload: "Paste a Bitcoin address, payment QR text, or base64 PSBT. Continue detects which type it is.",
            self.psbt_input: "A partially signed Bitcoin transaction from your online wallet. Core reviews its contents before signing is enabled.",
            self.psbt_review: "Check every recipient, amount, fee, and change output. The offline signer cannot check these against a local blockchain.",
            self.signer_password: "The password that encrypts this session’s Core wallet file. It is cleared after each signing attempt.",
            self.signed_psbt: "The transaction with this signer’s signatures. Transfer it to the other signers or your online wallet; it has not been broadcast.",
            self.verify_address_input: "Enter a Bitcoin address or bitcoin: payment URI. Core checks whether the address belongs to this wallet.",
            self.verified_address_label: "An optional note saved after Core verifies the address. It lasts only for this cold session.",
            self.theme_button: "Switch between light and dark appearance.",
            self.settings_theme_button: "Switch between light and dark appearance.",
            self.create_choice: "Create a new recovery phrase for this signer.",
            self.recover_choice: "Restore a signer using an existing BIP39 recovery phrase and any BIP39 passphrase.",
            self.single_choice: "One private key is enough to sign for this wallet.",
            self.multi_choice: "Several signers share a wallet. You choose how many signatures a transaction needs.",
            self.bip39_show: "Show or hide the BIP39 passphrase while you enter it.",
            self.wallet_show: "Show or hide the temporary wallet-file password while you enter it.",
            self.show_signer_password: "Show or hide the wallet password before signing.",
            self.address_table: "Double-click a saved address to view its QR or edit its label. This list lasts only for the current cold session.",
        }
        for widget, explanation in fields.items():
            widget.setToolTip(explanation)
        descriptions = {
            "Generate recovery phrase": "Generate a recovery phrase from Bitcoin Core wallet data, Linux randomness, and optional dice rolls.",
            "Generate address": "Ask Core for a fresh receiving address and save it in this session’s address list.",
            "I wrote it down": "Hide the phrase and check that you can retype every word from your backup.",
            "Skip confirmation (testing)": "Development only: continue without checking your written recovery phrase. Use test wallets only.",
            "+ Add signer": "Add another signer to the multisig policy. This flow supports up to 20 signers.",
            "− Remove last": "Remove the last external signer from this policy. At least two signers must remain.",
            "Start camera scan": "Open the system QR scanner. It reads one address or transaction QR at a time.",
            "Scan QR with zbarcam": "Open the system camera scanner and read one static QR code.",
            "Import file…": "Load a binary or base64 PSBT file of up to 2 MiB for review.",
            "Review transaction": "Ask Core to decode the PSBT and display every output and the fee. This does not sign it.",
            "Sign reviewed transaction": "Sign only the exact transaction shown in the review. Core does not finalize or broadcast it.",
            "Save signed PSBT…": "Save the signed PSBT as base64 text for transfer to another signer or the online wallet.",
            "Verify address": "Ask Core whether this address belongs to the selected wallet. A match does not show whether it has received funds.",
        }
        next_steps = {
            0: "Continue to create or recover the phrase for the selected wallet type.",
            2: "Check the recovery phrase and continue. If the last word is missing, first choose it from your backup.",
            4: "Check every entered word against the generated phrase before continuing.",
            5: "Import the complete multisig policy into Core and verify its first receiving address.",
            9: "Detect the pasted QR data and check the address or review the transaction.",
            15: "Continue with the selected new-wallet or recovery option.",
            16: "Continue with the selected single-signature or multisig wallet type.",
            17: "Apply the selected protection and load the signer into Core. Multisig setup then asks for the other public keys.",
        }
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QPushButton, QLineEdit, QComboBox, QSpinBox, QCheckBox, QPlainTextEdit, QTableWidget, ActionRow)):
                if isinstance(widget.parentWidget(), (QComboBox, QSpinBox)):
                    widget.setToolTip(widget.parentWidget().toolTip())
                if isinstance(widget, QPushButton):
                    text = widget.text()
                    page = next((index for index in range(self.stack.count())
                                 if self.stack.widget(index).isAncestorOf(widget)), None)
                    if text in descriptions:
                        widget.setToolTip(descriptions[text])
                    elif text.startswith("Continue"):
                        widget.setToolTip(next_steps[page])
                    elif "Back" in text:
                        widget.setToolTip("Close this unfinished signer session and return to wallet selection."
                                          if page in (5, 15) else "Return to the previous wallet screen without completing this step.")
                    elif text == "Done":
                        widget.setToolTip("Save this address and its label for the current session, then return to the wallet."
                                          if page == 8 else "Save the label in Core and return to this session’s address list.")
                self.help_targets.append(widget)
                widget.installEventFilter(self)

    def _build_psbt_page(self):
        layout = self._card(scroll=True)
        title = _label("Review and sign a transaction", False)
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(_label(
            "Import a PSBT, verify every recipient, amount, fee and change output, then sign. "
            "Input amounts and fee come from the PSBT, not a local blockchain. This signer never broadcasts.", True
        ))
        self.psbt_input = QPlainTextEdit()
        self.psbt_input.setPlaceholderText("Paste a base64 PSBT, import a file, or scan one QR code")
        self.psbt_input.setMaximumHeight(115)
        self.psbt_input.textChanged.connect(self._invalidate_psbt_review)
        layout.addWidget(self.psbt_input)
        controls = QHBoxLayout()
        scan = QPushButton("Scan QR with zbarcam")
        scan.clicked.connect(self._start_qr_scanner)
        controls.addWidget(scan)
        load = QPushButton("Import file…")
        load.clicked.connect(self._load_psbt_file)
        controls.addWidget(load)
        review = QPushButton("Review transaction")
        review.setObjectName("Primary")
        review.clicked.connect(self._review_psbt)
        controls.addWidget(review)
        controls.addStretch()
        layout.addLayout(controls)
        self.psbt_review = QPlainTextEdit()
        self.psbt_review.setReadOnly(True)
        self.psbt_review.setPlaceholderText("Transaction details from Bitcoin Core will appear here.")
        self.psbt_review.setMaximumHeight(175)
        layout.addWidget(self.psbt_review)
        password_row = QHBoxLayout()
        self.signer_password = QLineEdit()
        self.signer_password.setPlaceholderText("Wallet password, if encrypted")
        self.signer_password.setEchoMode(QLineEdit.EchoMode.Password)
        password_row.addWidget(self.signer_password)
        self.show_signer_password = QCheckBox("Show")
        self.show_signer_password.toggled.connect(
            lambda visible: self.signer_password.setEchoMode(
                QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
            )
        )
        password_row.addWidget(self.show_signer_password)
        layout.addLayout(password_row)
        self.sign_button = QPushButton("Sign reviewed transaction")
        self.sign_button.setObjectName("Primary")
        self.sign_button.setEnabled(False)
        self.sign_button.clicked.connect(self._sign_reviewed_psbt)
        layout.addWidget(self.sign_button, 0, Qt.AlignmentFlag.AlignRight)
        signed_row = QHBoxLayout()
        self.signed_qr = QLabel()
        self.signed_qr.setFixedSize(320, 320)
        self.signed_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signed_qr.hide()
        signed_row.addWidget(self.signed_qr, 0, Qt.AlignmentFlag.AlignTop)
        signed_details = QVBoxLayout()
        self.signed_status = _label("")
        signed_details.addWidget(self.signed_status)
        self.signed_psbt = QPlainTextEdit()
        self.signed_psbt.setReadOnly(True)
        self.signed_psbt.setPlaceholderText("Signed PSBT will appear here.")
        self.signed_psbt.setMaximumHeight(110)
        signed_details.addWidget(self.signed_psbt)
        save = QPushButton("Save signed PSBT…")
        save.clicked.connect(self._save_signed_psbt)
        signed_details.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        signed_row.addLayout(signed_details, 1)
        layout.addLayout(signed_row)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("Back to wallet")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(6))
        footer.addWidget(back)
        footer.addStretch()
        layout.addLayout(footer)

    def _build_verify_address_page(self):
        layout = self._card()
        title = _label("Verify a receive address", False)
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(_label("Confirm this address belongs to the selected wallet.", True))
        self.verify_address_input = QLineEdit()
        self.verify_address_input.setPlaceholderText("Bitcoin address or bitcoin: URI")
        self.verify_address_input.textChanged.connect(self._clear_address_result)
        layout.addWidget(self.verify_address_input)
        controls = QHBoxLayout()
        scan = QPushButton("Scan QR with zbarcam")
        scan.clicked.connect(lambda: self._start_qr_scanner(self.verify_address_input))
        controls.addWidget(scan)
        verify = QPushButton("Verify address")
        verify.setObjectName("Primary")
        verify.clicked.connect(self._verify_receive_address)
        controls.addWidget(verify)
        controls.addStretch()
        layout.addLayout(controls)
        self.verify_result = _label("")
        self.verify_result.setObjectName("Verification")
        layout.addWidget(self.verify_result)
        self.verified_address_label = QLineEdit()
        self.verified_address_label.setPlaceholderText("Label · optional")
        self.verified_address_label.setEnabled(False)
        layout.addWidget(self.verified_address_label)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("Back to wallet")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(9))
        footer.addWidget(back)
        footer.addStretch()
        done = QPushButton("Done")
        done.setObjectName("Primary")
        done.clicked.connect(self._save_verified_address)
        footer.addWidget(done)
        layout.addLayout(footer)

    def _toggle_bip39_fields(self, enabled):
        for widget in (self.bip39_passphrase1, self.bip39_passphrase2, self.bip39_show):
            widget.setEnabled(enabled)
            widget.setVisible(enabled and (widget is not self.bip39_passphrase2 or self.phrase_source != "recover"))
        if not enabled:
            self.bip39_passphrase1.clear()
            self.bip39_passphrase2.clear()

    def _toggle_bip39_visibility(self, visible):
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.bip39_passphrase1.setEchoMode(mode)
        self.bip39_passphrase2.setEchoMode(mode)

    def _toggle_wallet_fields(self, enabled):
        for widget in (self.wallet_password1, self.wallet_password2, self.wallet_show):
            widget.setEnabled(enabled)
            widget.setVisible(enabled)
        if not enabled:
            self.wallet_password1.clear()
            self.wallet_password2.clear()

    def _toggle_wallet_visibility(self, visible):
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.wallet_password1.setEchoMode(mode)
        self.wallet_password2.setEchoMode(mode)

    def _read_protection_options(self):
        bip39_passphrase = ""
        wallet_password = ""
        if self.use_bip39_passphrase.isChecked():
            first, second = self.bip39_passphrase1.text(), self.bip39_passphrase2.text()
            if not first or (self.phrase_source != "recover" and first != second):
                message = "Enter your BIP39 passphrase." if self.phrase_source == "recover" else "Enter the same non-empty BIP39 passphrase twice."
                QMessageBox.warning(self, "Check BIP39 passphrase", message)
                return None
            bip39_passphrase = first
        if self.encrypt_wallet.isChecked():
            first, second = self.wallet_password1.text(), self.wallet_password2.text()
            if len(first) < 10 or first != second:
                QMessageBox.warning(self, "Check wallet password", "Enter the same wallet password twice. Use at least 10 characters.")
                return None
            wallet_password = first
        self.current_bip39_passphrase = bip39_passphrase
        self.current_wallet_passphrase = wallet_password
        return True

    def _reset_protection(self):
        self.current_bip39_passphrase = ""
        self.current_wallet_passphrase = ""
        self.use_bip39_passphrase.setChecked(False)
        self.encrypt_wallet.setChecked(False)
        self.bip39_show.setChecked(False)
        self.wallet_show.setChecked(False)
        for field in (self.bip39_passphrase1, self.bip39_passphrase2, self.wallet_password1, self.wallet_password2):
            field.clear()

    def _show_protection(self):
        self._reset_protection()
        self._toggle_bip39_fields(False)
        self.stack.setCurrentIndex(17)

    def _start_new_wallet(self):
        if self.core is None:
            return
        try:
            if self.wallet_digest is None:
                self.wallet_digest = self.core.create_entropy_wallet_hash()
                self.os_entropy = secrets.token_bytes(32)
        except ColdSetupError as exc:
            QMessageBox.critical(self, "Temporary wallet failed", str(exc))
            return
        self._update_entropy_audit()
        self.audit_toggle.setChecked(False)
        self.stack.setCurrentIndex(1)

    def _start_recovery(self):
        if self.core is None:
            return
        self._clear_recovery_candidates()
        self.recovery_text.clear()
        self.stack.setCurrentIndex(2)

    def _open_core(self, bitcoind):
        try:
            self.core = OfflineCore(bitcoind, self.session_id, dev_keep_network=self.dev_keep_network).start()
        except (ColdSetupError, OSError) as exc:
            QMessageBox.critical(self, "Cold signer setup failed", str(exc))
            self.reject()

    def _update_entropy_audit(self, *_args):
        if self.wallet_digest is None or self.os_entropy is None:
            self.entropy_audit.clear()
            return
        dice = "".join(self.dice.text().split())
        count = int(self.word_count.currentData())
        try:
            digest = entropy_from_sources(self.wallet_digest, 24, dice, os_entropy=self.os_entropy)
        except SeedError as exc:
            self.entropy_audit.setPlainText(str(exc))
            return
        size = count * 4 // 3
        command = (
            'python3 -c "from hashlib import sha256; '
            f"rng=bytes.fromhex('{self.os_entropy.hex()}'); "
            f"wallet=bytes.fromhex('{self.wallet_digest.hex()}'); dice=b'{dice}'; "
            "data=(b'Core Companion BIP39 entropy v1\\x00'"
            "+len(wallet).to_bytes(2,'big')+wallet"
            "+len(rng).to_bytes(2,'big')+rng"
            "+len(dice).to_bytes(4,'big')+dice); "
            f"print(sha256(data).digest()[:{size}].hex())" + '"'
        )
        self.entropy_audit.setPlainText(
            f"OS RNG (hex): {self.os_entropy.hex()}\n"
            f"Wallet.dat SHA-256: {self.wallet_digest.hex()}\n"
            f"Dice rolls: {dice or '(none)'}\n\n"
            "SHA-256 command:\n" + command + "\n\n"
            f"Starting entropy ({size * 8} bits): {digest[:size].hex()}"
        )

    def _generate_phrase(self):
        if self.wallet_digest is None or self.os_entropy is None:
            return
        try:
            entropy = entropy_from_sources(
                self.wallet_digest,
                int(self.word_count.currentData()),
                self.dice.text(),
                os_entropy=self.os_entropy,
            )
            self.phrase = phrase_from_entropy(entropy)
        except SeedError as exc:
            QMessageBox.warning(self, "Check the dice rolls", str(exc))
            return
        self.words = self.phrase.split()
        self.phrase_source = "create"
        self._render_words()
        self.stack.setCurrentIndex(3)

    def _render_words(self):
        _clear_layout(self.word_grid)
        self.word_labels = []
        rows = (len(self.words) + 1) // 2
        for index, word in enumerate(self.words):
            column = 0 if index < rows else 1
            row = index if column == 0 else index - rows
            item = QLabel(f"{index + 1:02d}   {word}")
            item.setFont(fixed_font(12))
            item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            self.word_grid.addWidget(item, row, column)
            self.word_labels.append(item)

    def _clear_recovery_candidates(self):
        self.recovery_prefix = None
        self.recovery_hint.clear()
        self.final_word.clear()
        self.final_word.hide()

    def _continue_recovery(self):
        count = int(self.recovery_count.currentData())
        tokens = " ".join(self.recovery_text.toPlainText().split()).split()
        if len(tokens) == count:
            try:
                self.phrase = validate_phrase(" ".join(tokens))
            except SeedError as exc:
                QMessageBox.warning(self, "Phrase checksum failed", str(exc))
                return
        elif len(tokens) == count - 1:
            prefix = " ".join(tokens)
            if self.recovery_prefix != prefix:
                try:
                    candidates = final_word_candidates(prefix)
                except SeedError as exc:
                    QMessageBox.warning(self, "Recovery phrase", str(exc))
                    return
                if not candidates:
                    QMessageBox.warning(self, "No checksum match", "No final word matches this phrase. Check the words and order.")
                    return
                self.final_word.clear()
                self.final_word.addItems(candidates)
                self.final_word.show()
                self.recovery_prefix = prefix
                self.recovery_hint.setText(
                    f"{len(candidates)} checksum-valid final words. Choose the final word from your backup, then continue again."
                )
                return
            self.phrase = validate_phrase(prefix + " " + self.final_word.currentText())
        else:
            QMessageBox.warning(
                self,
                "Recovery phrase length",
                f"Enter {count} words, or enter the first {count - 1} and choose the final word.",
            )
            return
        self.words = self.phrase.split()
        self.phrase_source = "recover"
        self._show_protection()

    def _show_confirmation(self):
        self.challenge = list(range(len(self.words)))
        _clear_layout(self.challenge_form)
        self.challenge_fields = []
        for index in self.challenge:
            field = QLineEdit()
            field.setPlaceholderText(f"Word {index + 1}")
            field.setToolTip(f"Enter word {index + 1} from your written backup, keeping the original order.")
            field.installEventFilter(self)
            self.challenge_form.addWidget(field, index // 3, index % 3)
            self.challenge_fields.append(field)
        for item in self.word_labels:
            item.clear()
        self.stack.setCurrentIndex(4)

    def _back_from_confirmation(self):
        if self.phrase_source == "recover":
            self.stack.setCurrentIndex(2)
        else:
            self._render_words()
            self.stack.setCurrentIndex(3)

    def _confirm_phrase(self):
        if not self.phrase:
            return
        for position, field in zip(self.challenge, self.challenge_fields):
            entered = unicodedata.normalize("NFKD", field.text().strip()).casefold()
            expected = unicodedata.normalize("NFKD", self.words[position]).casefold()
            if entered != expected:
                QMessageBox.warning(self, "Phrase doesn’t match", "One or more words are incorrect. Check your written phrase and try again.")
                return
        self._show_protection()

    def _add_signer_fields(self, suggested_label):
        row = len(self.signer_fields)
        name = QLineEdit(suggested_label)
        name.setPlaceholderText("Signer label")
        key = QLineEdit()
        key.setPlaceholderText("[fingerprint/87h/0h/0h]xpub…")
        key.setFont(fixed_font(9))
        scan = QPushButton("Scan")
        scan.clicked.connect(lambda checked=False, field=key: self._start_qr_scanner(field))
        self.signer_grid.addWidget(QLabel(f"External {row + 1}"), row, 0)
        self.signer_grid.addWidget(name, row, 1)
        self.signer_grid.addWidget(key, row, 2)
        self.signer_grid.addWidget(scan, row, 3)
        self.signer_fields.append((name, key, scan))
        for widget, tip in (
            (name, "A short label to identify this signer in the wallet policy."),
            (key, "The signer’s BIP87 account xpub, including its fingerprint and derivation origin."),
            (scan, "Scan this signer’s public account key QR."),
        ):
            widget.setToolTip(tip)
            widget.installEventFilter(self)
        self._sync_threshold()

    def _add_signer(self):
        if len(self.signer_fields) >= 19:
            return
        self._add_signer_fields(f"Signer {len(self.signer_fields) + 2}")

    def _remove_signer(self):
        if len(self.signer_fields) <= 1:
            return
        name, key, scan = self.signer_fields.pop()
        for widget in (name, key, scan):
            self.signer_grid.removeWidget(widget)
            widget.deleteLater()
        label_item = self.signer_grid.itemAtPosition(len(self.signer_fields), 0)
        if label_item and label_item.widget():
            label_item.widget().deleteLater()
        self._sync_threshold()

    def _sync_threshold(self):
        total = len(self.signer_fields) + 1
        self.threshold.setMaximum(total)
        if self.threshold.value() > total:
            self.threshold.setValue(total)
        self.signer_count_label.setText(f"{total} signers total")

    def _create_single_signature(self):
        try:
            result = self.core.create_single_sig_wallet(
                self.phrase,
                self.address_type.currentData(),
                self.current_wallet_passphrase,
                self.current_bip39_passphrase,
            )
        except (SeedError, ColdSetupError) as exc:
            self._reset_protection()
            QMessageBox.critical(self, "Core wallet setup failed", str(exc))
            return
        self._show_complete(result, "Single-signature")

    def _signer_details(self):
        signers = []
        own_label = self.own_signer_name.text().strip()
        if not own_label:
            QMessageBox.warning(self, "Signer label", "Enter a label for this signer.")
            return
        seen_labels = {own_label.casefold()}
        for name, key, _scan in self.signer_fields:
            signer_label = name.text().strip()
            signer_key = key.text().strip()
            if not signer_label or not signer_key:
                QMessageBox.warning(self, "Complete signer details", "Enter a label and BIP87 account xpub for every other signer.")
                return
            if signer_label.casefold() in seen_labels:
                QMessageBox.warning(self, "Signer labels", "Each signer needs a different label.")
                return
            seen_labels.add(signer_label.casefold())
            signers.append({"label": signer_label, "key": signer_key})
        return signers

    def _create_multisig(self):
        signers = self._signer_details()
        if signers is None:
            return
        password = self.multisig_password.text() if self.wallet_encrypted else ""
        if self.wallet_encrypted and not password:
            QMessageBox.warning(self, "Wallet password required", "Enter the wallet password to finish setup.")
            return
        try:
            result = self.core.complete_multisig_wallet(
                self.threshold.value(),
                signers,
                password,
                self.own_signer_name.text().strip(),
            )
        except ColdSetupError as exc:
            QMessageBox.critical(self, "Core wallet setup failed", str(exc))
            return
        finally:
            self.multisig_password.clear()
        self._show_complete(result, f"{self.threshold.value()} of {len(signers) + 1} multisig · BIP87")

    def _prepare_multisig(self):
        try:
            result = self.core.prepare_multisig_key(
                self.phrase, self.current_wallet_passphrase, self.current_bip39_passphrase,
            )
        except (SeedError, ColdSetupError) as exc:
            self._reset_protection()
            QMessageBox.critical(self, "Core wallet setup failed", str(exc))
            return
        self.multisig_prepared = True
        self.wallet_encrypted = result["encrypted"]
        self.multisig_own_key.setPlainText(result["own_account_key"])
        self.multisig_key_qr.setPixmap(self._qr_pixmap(result["own_account_key"], size=260))
        self.multisig_password.setVisible(self.wallet_encrypted)
        self._clear_setup_secrets()
        self.stack.setCurrentIndex(5)

    def _clear_setup_secrets(self):
        self.phrase = None
        self.words.clear()
        self.recovery_text.clear()
        self.wallet_digest = None
        self.os_entropy = None
        self.entropy_audit.clear()
        self.dice.clear()
        self._reset_protection()
        for item in self.word_labels:
            item.clear()
        for field in self.challenge_fields:
            field.clear()

    def _show_complete(self, result, wallet_type):
        self._clear_setup_secrets()
        self.wallet_ready = True
        self.wallet_encrypted = result.get("encrypted") is True
        self.signer_password.setEnabled(self.wallet_encrypted)
        self.show_signer_password.setEnabled(self.wallet_encrypted)
        self.descriptors.setPlainText("\n".join(result["descriptors"]))
        self.wallet_display_name = self.wallet_name_input.text().strip() or "Cold signer"
        self.setWindowTitle(f"Core Companion — {self.wallet_display_name}")
        self.wallet_fingerprint = str(result.get("address_info", {}).get("hdmasterfingerprint", "")).upper()
        own_key = result.get("own_account_key", "")
        if not self.wallet_fingerprint and own_key.startswith("[") and "/" in own_key:
            self.wallet_fingerprint = own_key[1:9].upper()
        self.identity_name.setText(self.wallet_display_name)
        self.identity_policy.setText(wallet_type)
        self.identity_fingerprint.setText(
            f"Signer · {self.wallet_fingerprint}" if self.wallet_fingerprint else "Signer fingerprint unavailable from Core"
        )
        self.policy_identity.setText(
            f"{self.wallet_display_name}  ·  {wallet_type}\n"
            + (f"Signer fingerprint · {self.wallet_fingerprint}" if self.wallet_fingerprint else "Signer fingerprint unavailable from Core")
        )
        self.status_left.setText(f"{self.wallet_display_name} · {wallet_type}")
        self.status_right.setText(f"Signer {self.wallet_fingerprint}" if self.wallet_fingerprint else "Cold signer · offline")
        self._update_identity_mark()
        signer_map = result.get("signers", [])
        if signer_map:
            lines = ["SIGNERS"]
            for index, item in enumerate(signer_map, 1):
                fingerprint = item["key"][1:9] if item.get("key", "").startswith("[") else ""
                lines.append(f"{index}. {item['label']}  ·  {fingerprint}")
            signer_text = "\n".join(lines)
        else:
            signer_text = "Single-signature · one signer"
        if own_key:
            signer_text += "\n\nYour BIP87 account key\n" + own_key
        self.signer_map.setText(signer_text)
        self.wallet_type_summary = wallet_type
        self.stack.setCurrentIndex(6)

    def _update_identity_mark(self):
        fingerprint = self.wallet_fingerprint or "00000000"
        try:
            bits = f"{int(fingerprint, 16):032b}"[-25:]
        except ValueError:
            bits = "0" * 25
        for index, tile in enumerate(self.identity_tiles):
            tile.setProperty("lit", bits[index] == "1")
            tile.style().unpolish(tile)
            tile.style().polish(tile)

    def _change_wallet(self):
        self._finish()

    def _toggle_help_mode(self):
        self.help_mode = not self.help_mode
        self.help_button.set_caption("Help on" if self.help_mode else "Help")
        self.help_button.setProperty("active", self.help_mode)
        self.help_button.style().unpolish(self.help_button)
        self.help_button.style().polish(self.help_button)

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.setStyleSheet(stylesheet(self.dark_mode))
        caption = "Light mode" if self.dark_mode else "Dark mode"
        glyph = "light" if self.dark_mode else "dark"
        for control in (self.theme_button, self.settings_theme_button):
            control.set_caption(caption)
            control.set_glyph(glyph)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Enter and self.help_mode and watched.toolTip():
            point = watched.mapToGlobal(watched.rect().bottomLeft())
            QToolTip.showText(point, watched.toolTip(), watched)
        elif event.type() == QEvent.Type.Leave and self.help_mode:
            QToolTip.hideText()
        return super().eventFilter(watched, event)

    def _open_addresses(self):
        self._refresh_address_table()
        self.stack.setCurrentIndex(10)

    def _refresh_address_table(self):
        self.address_table.setRowCount(len(self.address_records))
        for row, record in enumerate(self.address_records):
            label_item = QTableWidgetItem(record.get("label") or "Unlabeled")
            address_item = QTableWidgetItem(record["address"])
            address_item.setFont(fixed_font(9))
            used_item = QTableWidgetItem("✓" if record.get("used") else "—")
            for item in (label_item, address_item, used_item):
                item.setData(Qt.ItemDataRole.UserRole, record["address"])
            self.address_table.setItem(row, 0, label_item)
            self.address_table.setItem(row, 1, address_item)
            self.address_table.setItem(row, 2, used_item)

    def _generate_receive_address(self):
        if self.core is None:
            return
        try:
            result = self.core.new_receive_address()
        except ColdSetupError as exc:
            QMessageBox.warning(self, "Address generation failed", str(exc))
            return
        record = {"address": result["address"], "label": "", "used": True}
        self.address_records = [item for item in self.address_records if item["address"] != record["address"]]
        self.address_records.insert(0, record)
        self._show_address_detail(record)

    def _open_address_from_row(self, row, _column):
        item = self.address_table.item(row, 1)
        if not item:
            return
        address = item.data(Qt.ItemDataRole.UserRole)
        record = next((entry for entry in self.address_records if entry["address"] == address), None)
        if record:
            self._show_address_detail(record)

    def _show_address_detail(self, record):
        self.active_address = record["address"]
        self.address_detail_title.setText(record.get("label") or "Wallet address")
        self.address_detail_value.setText(record["address"])
        self.address_detail_label.setText(record.get("label", ""))
        self.address_used_status.setText("Saved on this signer")
        self.address_qr.setPixmap(self._qr_pixmap(record["address"], size=320))
        self.stack.setCurrentIndex(11)

    def _save_address_detail(self):
        record = next((entry for entry in self.address_records if entry["address"] == self.active_address), None)
        if not record or self.core is None:
            return
        label = self.address_detail_label.text().strip()
        try:
            self.core.set_address_label(record["address"], label)
        except ColdSetupError as exc:
            QMessageBox.warning(self, "Could not save label", str(exc))
            return
        record["label"] = label
        self._open_addresses()

    def _save_verified_address(self):
        address = self.verify_address_input.text().strip()
        if not address or self.verify_result.property("verified") is not True:
            self.stack.setCurrentIndex(9)
            return
        label = self.verified_address_label.text().strip()
        try:
            self.core.set_address_label(address, label)
        except ColdSetupError as exc:
            QMessageBox.warning(self, "Could not save address", str(exc))
            return
        record = next((entry for entry in self.address_records if entry["address"] == address), None)
        if record is None:
            record = {"address": address, "used": True}
            self.address_records.insert(0, record)
        record["label"] = label
        self.verify_address_input.clear()
        self.verified_address_label.clear()
        self.stack.setCurrentIndex(6)

    def _invalidate_psbt_review(self):
        self.reviewed_psbt = None
        self.reviewed_id = None
        self.sign_button.setEnabled(False)
        self.psbt_review.clear()
        self.signed_psbt.clear()
        self.signed_status.clear()
        self.signed_qr.clear()
        self.signed_qr.hide()

    def _load_psbt_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import a PSBT", "", "PSBT or text files (*.psbt *.txt);;All files (*)")
        if not path:
            return
        try:
            with Path(path).open("rb") as source:
                raw = source.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("The selected file is larger than 2 MiB.")
            if raw.startswith(b"psbt\xff"):
                text = base64.b64encode(raw).decode("ascii")
            else:
                text = raw.decode("ascii").strip()
            if len(text) > 2 * 1024 * 1024:
                raise ValueError("The encoded PSBT is larger than 2 MiB.")
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, "Could not import PSBT", str(exc))
            return
        self.psbt_input.setPlainText(text)

    def _start_qr_scanner(self, target_field=None):
        if self.scanner:
            return
        self.scanner_target_field = target_field
        self.scanner = QRScanner(self)
        self.scanner.decoded.connect(self._scanner_data)
        self.scanner.failed.connect(self._scanner_error)
        self.scanner.scan()

    def _stop_scanner(self):
        if self.scanner:
            scanner, self.scanner = self.scanner, None
            scanner.stop()
            scanner.deleteLater()

    def _scanner_data(self, text):
        self._stop_scanner()
        if not text.isascii():
            QMessageBox.warning(self, "Unsupported QR payload", "Scan a Bitcoin address, public key or base64 PSBT.")
            return
        target_field, self.scanner_target_field = self.scanner_target_field, None
        if target_field is not None:
            target_field.setText(text)
            if target_field is self.verify_address_input:
                self._verify_receive_address()
            elif target_field is self.scan_payload:
                self._process_scanned_payload()
        else:
            self.psbt_input.setPlainText(text)
            self._review_psbt()

    def _process_scanned_payload(self):
        raw = self.scan_payload.text().strip()
        if not raw:
            return
        if raw.casefold().startswith("bitcoin:"):
            parsed = urlsplit(raw)
            if parsed.scheme.casefold() != "bitcoin" or parsed.netloc or parsed.fragment:
                QMessageBox.warning(self, "Unsupported QR data", "This QR does not contain a standard Bitcoin address URI.")
                return
            self.verify_address_input.setText(unquote(parsed.path))
            self.stack.setCurrentIndex(8)
            self._verify_receive_address()
            return
        if raw.casefold().startswith(("bc1", "1", "3")) and len(raw) <= 128:
            self.verify_address_input.setText(raw)
            self.stack.setCurrentIndex(8)
            self._verify_receive_address()
            return
        self.psbt_input.setPlainText(raw)
        self.stack.setCurrentIndex(7)
        self._review_psbt()

    def _scanner_error(self, message):
        self._stop_scanner()
        QMessageBox.warning(self, "QR scanner", message)

    def _verify_receive_address(self):
        raw = self.verify_address_input.text().strip()
        if not raw:
            QMessageBox.information(self, "Address required", "Scan or enter an address first.")
            return
        address = raw
        if raw.casefold().startswith("bitcoin:"):
            parsed = urlsplit(raw)
            if parsed.scheme.casefold() != "bitcoin" or parsed.netloc or parsed.fragment:
                QMessageBox.warning(self, "Unsupported payment QR", "This QR does not contain a standard Bitcoin address URI.")
                return
            address = unquote(parsed.path)
        try:
            belongs = self.core.verify_address(address)
        except ColdSetupError as exc:
            self.verify_result.setText(str(exc))
            self.verify_result.setProperty("verified", False)
            self.verify_result.style().unpolish(self.verify_result)
            self.verify_result.style().polish(self.verify_result)
            self.verified_address_label.setEnabled(False)
            return
        self.verify_address_input.setText(address)
        if belongs:
            self.verify_result.setText(f"Address belongs to {self.wallet_display_name}.")
            self.verify_result.setProperty("verified", True)
            self.verified_address_label.setEnabled(True)
        else:
            self.verify_result.setText("This address does not belong to the current wallet.")
            self.verify_result.setProperty("verified", False)
            self.verified_address_label.setEnabled(False)
        self.verify_result.style().unpolish(self.verify_result)
        self.verify_result.style().polish(self.verify_result)

    def _clear_address_result(self):
        self.verify_result.clear()
        self.verify_result.setProperty("verified", False)
        self.verified_address_label.clear()
        self.verified_address_label.setEnabled(False)
        self.verify_result.style().unpolish(self.verify_result)
        self.verify_result.style().polish(self.verify_result)

    def _review_psbt(self):
        if self.core is None:
            return
        self._invalidate_psbt_review()
        text = self.psbt_input.toPlainText().strip()
        if not text or len(text) > 2 * 1024 * 1024:
            QMessageBox.warning(self, "PSBT size", "Enter a base64 PSBT smaller than 2 MiB.")
            return
        try:
            review = self.core.review_psbt(text)
        except ColdSetupError as exc:
            QMessageBox.warning(self, "PSBT could not be reviewed", str(exc))
            return
        self.psbt_input.blockSignals(True)
        self.psbt_input.setPlainText(review["psbt"])
        self.psbt_input.blockSignals(False)
        self.reviewed_psbt = review["psbt"]
        self.reviewed_id = review["review_id"]
        lines = [
            f"{review['review_id_label']}: {review['review_id']}",
            f"Inputs: {review['inputs']}    Outputs: {len(review['outputs'])}",
            f"Version: {review['version']}    Locktime: {review['locktime']}",
        ]
        if review["fee"] is None:
            lines.append("Fee: not available from this PSBT")
        else:
            lines.append(f"Fee: {Decimal(str(review['fee'])):.8f} BTC")
        lines.append("")
        for index, output in enumerate(review["outputs"], 1):
            amount = output["amount"]
            amount_text = f"{Decimal(str(amount)):.8f} BTC" if amount is not None else "amount unavailable"
            role = "CHANGE · verified by Core" if output["is_change"] else (
                "OWN ADDRESS" if output["is_mine"] else "RECIPIENT · verify independently"
            )
            lines.extend((f"Output {index} · {role}", f"  {amount_text}", f"  {output['address']}"))
            if output["address"].startswith("(non-standard"):
                lines.append(f"  Script: {output['script']}")
        analysis = review.get("analysis", {})
        input_states = analysis.get("inputs", [])
        missing_utxos = sum(1 for item in input_states if item.get("has_utxo") is not True)
        if missing_utxos:
            lines.extend(("", f"Warning: Core could not verify UTXO details for {missing_utxos} input(s)."))
        self.psbt_review.setPlainText("\n".join(lines))
        self.sign_button.setEnabled(True)
        self.signed_status.setText("")

    def _sign_reviewed_psbt(self):
        if not self.reviewed_psbt or not self.reviewed_id:
            return
        password = self.signer_password.text() if self.wallet_encrypted else ""
        if self.wallet_encrypted and not password:
            QMessageBox.warning(self, "Wallet password required", "Enter this wallet’s encryption password to sign.")
            return
        try:
            result = self.core.sign_psbt(self.reviewed_psbt, password, self.reviewed_id)
        except ColdSetupError as exc:
            self.signer_password.clear()
            self.sign_button.setEnabled(False)
            QMessageBox.warning(self, "Signing failed", str(exc))
            return
        self.signer_password.clear()
        self.sign_button.setEnabled(False)
        self.signed_psbt.setPlainText(result["psbt"])
        completion = "All inputs have signatures" if result["complete"] else "Partially signed · additional signer(s) required"
        self.signed_status.setText(completion + ". The transaction was not finalized or broadcast.")
        try:
            self.signed_qr.setPixmap(self._qr_pixmap(result["psbt"]))
            self.signed_qr.show()
        except DataOverflowError:
            self.signed_qr.hide()
            self.signed_status.setText(
                completion + ". Too large for one QR code; save the signed PSBT to transfer it."
            )
        QTimer.singleShot(0, lambda: self.stack.widget(7).ensureWidgetVisible(
            self.signed_qr if not self.signed_qr.isHidden() else self.signed_status, 0, 20,
        ))

    def _save_signed_psbt(self):
        text = self.signed_psbt.toPlainText().strip()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save signed PSBT", "signed-transaction.psbt", "PSBT files (*.psbt);;Text files (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(text + "\n", encoding="ascii")
        except OSError as exc:
            QMessageBox.warning(self, "Could not save PSBT", str(exc))

    def _export_watchonly_wallet(self):
        descriptors = self.descriptors.toPlainText().splitlines()
        payload = json.dumps({"name": self.wallet_display_name, "descriptors": descriptors}, separators=(",", ":"))
        try:
            pixmap = self._qr_pixmap(payload, size=480)
        except (ValueError, DataOverflowError):
            pixmap = None
        if not hasattr(self, "export_qr"):
            layout = self._card(scroll=True)
            title = _label("Export watch-only wallet")
            title.setObjectName("Title")
            layout.addWidget(title)
            self.export_qr = QLabel()
            self.export_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.export_qr.setWordWrap(True)
            layout.addWidget(self.export_qr)
            self.export_text = QPlainTextEdit()
            self.export_text.setReadOnly(True)
            self.export_text.setMaximumHeight(110)
            self.export_text.setToolTip("Public wallet name and receive/change descriptors. Keep this backup for multisig recovery.")
            self.export_text.installEventFilter(self)
            layout.addWidget(self.export_text)
            footer = QHBoxLayout()
            back = QPushButton("Back")
            back.setToolTip("Return to Tools & Settings. The public wallet backup remains available here.")
            back.installEventFilter(self)
            back.clicked.connect(lambda: self.stack.setCurrentIndex(12))
            footer.addWidget(back)
            footer.addStretch()
            save = QPushButton("Save wallet backup…")
            save.setObjectName("Primary")
            save.setToolTip("Save the public wallet configuration. It contains no recovery phrase or private keys.")
            save.installEventFilter(self)
            save.clicked.connect(self._save_watchonly_wallet)
            footer.addWidget(save)
            layout.addLayout(footer)
            self.export_page_index = self.stack.count() - 1
        if pixmap is None:
            self.export_qr.setText("Too large for one QR code. Save the wallet backup or copy the public data below.")
        else:
            self.export_qr.setPixmap(pixmap)
        self.export_text.setPlainText(payload)
        self.stack.setCurrentIndex(self.export_page_index)

    def _save_watchonly_wallet(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save public wallet backup", "wallet-backup.json", "JSON files (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(self.export_text.toPlainText() + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Could not save wallet backup", str(exc))

    def _confirm_close(self):
        if not (self.wallet_ready or self.multisig_prepared or self.phrase):
            return True
        message = "This session and its address labels will be removed from RAM. Keep your recovery phrase and any BIP39 passphrase."
        if self.wallet_mode == "multisig":
            message += ("\n\nMultisig recovery also needs the complete wallet policy. Save the public wallet backup before closing."
                        if self.wallet_ready else "\n\nMultisig setup is unfinished. Your public signer key can be recreated from your phrase and passphrase.")
        prompt = QMessageBox(QMessageBox.Icon.Warning, "Close cold signer?", message, parent=self)
        prompt.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Close)
        prompt.setDefaultButton(QMessageBox.StandardButton.Cancel)
        export = prompt.addButton("Export wallet", QMessageBox.ButtonRole.ActionRole) if self.wallet_ready else None
        prompt.exec()
        if export is not None and prompt.clickedButton() is export:
            self._export_watchonly_wallet()
            return False
        clicked = prompt.clickedButton()
        return clicked is not None and prompt.standardButton(clicked) == QMessageBox.StandardButton.Close

    _qr_pixmap = staticmethod(qr_pixmap)

    def shutdown_core(self):
        self._stop_scanner()
        self._clear_setup_secrets()
        self.multisig_password.clear()
        self.signer_password.clear()
        if self.core is not None:
            self.core.close()
            self.core = None

    def _finish(self):
        if not self._confirm_close():
            return
        try:
            self.shutdown_core()
        except ColdSetupError as exc:
            QMessageBox.critical(self, "Cannot close cold Core", str(exc))
            return
        self.accept()

    def reject(self):
        if not self._confirm_close():
            return
        try:
            self.shutdown_core()
        except ColdSetupError as exc:
            QMessageBox.critical(self, "Cannot close cold Core", str(exc))
            return
        super().reject()

    def closeEvent(self, event):
        if not self._confirm_close():
            event.ignore()
            return
        try:
            self.shutdown_core()
        except ColdSetupError as exc:
            QMessageBox.critical(self, "Cannot close cold Core", str(exc))
            event.ignore()
            return
        event.accept()
