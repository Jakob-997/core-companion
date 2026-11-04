"""Short-lived Linux UI for creating or recovering a Core signing wallet."""

import base64
import hashlib
import json
import secrets
import unicodedata
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .qr import qr_pixmap
from .scanner import QRScanner
from qrcode.exceptions import DataOverflowError
from PySide6.QtCore import Qt, QEvent, QTimer, QSettings
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout,
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
    entropy_material,
    final_word_candidates,
    phrase_from_entropy,
    validate_phrase,
)
from .theme import stylesheet
from .widgets import ActionRow, ChoiceRow, ComboBox, EmptyTable, FingerprintMark, IconButton, LineIcon, ScanIllustration, fixed_font


def _label(text, muted=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if muted:
        widget.setObjectName("Muted")
    return widget


def _heading(layout, eyebrow, title, description=""):
    caption = _label(eyebrow)
    caption.setObjectName("SectionLabel")
    layout.addWidget(caption)
    heading = _label(title)
    heading.setObjectName("Title")
    layout.addWidget(heading)
    if description:
        detail = _label(description)
        detail.setObjectName("PageDescription")
        layout.addWidget(detail)


def _panel(layout, title="", hint=""):
    panel = QFrame()
    panel.setObjectName("FormPanel")
    content = QVBoxLayout(panel)
    content.setContentsMargins(22, 20, 22, 20)
    content.setSpacing(14)
    if title:
        heading = _label(title)
        heading.setObjectName("FormTitle")
        content.addWidget(heading)
    if hint:
        detail = _label(hint)
        detail.setObjectName("FormHint")
        content.addWidget(detail)
    layout.addWidget(panel)
    return content


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


class ColdSignerDialog(QDialog):
    def __init__(self, bitcoind, session_id, parent=None, *, dev_keep_network=False):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setObjectName("ColdSigner")
        self.setWindowTitle("Core Companion — Cold storage")
        self.resize(1280, 850)
        self.setMinimumSize(980, 680)
        self.dark_mode = False
        self.setStyleSheet(stylesheet())
        self.core = None
        self.startup_error = None
        self.wallet_digest = None
        self.os_entropy = None
        self.phrase = None
        self.words = []
        self.recovery_fields = []
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
        self.hidden_addresses = []
        self.active_address = None
        self.help_targets = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 12)
        root.setSpacing(14)
        header = QHBoxLayout()
        mark = LineIcon("bitcoin", "Mark", stroke_width=1.9, inset=4)
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.global_back = IconButton("back", "Back", self._go_back)
        header.addWidget(self.global_back)
        header.addWidget(mark)
        brand = _label("Core Companion", False)
        brand.setObjectName("Brand")
        header.addWidget(brand)
        mode = _label("COLD STORAGE")
        mode.setObjectName("HeaderMode")
        header.addSpacing(16)
        header.addWidget(mode)
        header.addStretch()
        self.help_button = IconButton(
            "i", "Help", self._toggle_help_mode,
            tooltip="Turn on instant explanations. Hover over a control to see what it does.",
        )
        header.addWidget(self.help_button)
        self.theme_button = IconButton("dark", "Dark mode", self._toggle_theme)
        header.addWidget(self.theme_button)
        header.addWidget(IconButton("settings", "Settings", self._open_settings))
        self.close_button = IconButton(
            "close", "Close", self.close,
            tooltip="Close the signer, save the wallet and stop temporary Core.",
        )
        header.addWidget(self.close_button)
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
        self.workflow = QFrame()
        self.workflow.setObjectName("WorkflowBar")
        steps = QHBoxLayout(self.workflow)
        steps.setContentsMargins(22, 10, 22, 10)
        steps.setSpacing(24)
        self.workflow_steps = []
        for index, text in enumerate(("Wallet", "Recovery", "Protection", "Policy"), 1):
            step = _label(f"{index:02d}  {text}")
            step.setObjectName("StepLabel")
            step.setWordWrap(False)
            steps.addWidget(step)
            self.workflow_steps.append(step)
        steps.addStretch()
        root.addWidget(self.workflow)
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
        self.status_left = _label("TEST VM · NOT AIR-GAPPED" if self.dev_keep_network else "Permanent offline signer", True)
        self.status_right = _label("Setup", True)
        self.status_left.setWordWrap(False)
        self.status_right.setWordWrap(False)
        status = QHBoxLayout()
        status.addWidget(self.status_left)
        status.addStretch()
        status.addWidget(self.status_right)
        root.addLayout(status)
        for control in self.findChildren(QPushButton):
            control.setAutoDefault(False)
        self._install_help_targets()
        self.stack.currentChanged.connect(self._update_workflow)
        self.stack.setCurrentIndex(15)
        self._update_workflow(15)
        self._open_core(bitcoind)
        self._refresh_saved_wallets()
        self.stack.currentChanged.connect(self._page_changed)
        for control in self.findChildren(QPushButton):
            if control.text().startswith(("Back", "‹  Back")):
                control.hide()
        self.global_back.show()

    def _update_workflow(self, page):
        stages = {15: 0, 16: 0, 0: 0, 1: 1, 2: 1, 3: 1, 4: 1, 17: 2, 5: 3}
        self.workflow.setVisible(page in stages)
        stage = stages.get(page, 0)
        for index, label in enumerate(self.workflow_steps):
            label.setVisible(index < 3 or self.wallet_mode == "multisig")
            label.setProperty("state", "current" if index == stage else "complete" if index < stage else "upcoming")
            label.style().unpolish(label)
            label.style().polish(label)

    def _card(self, *, scroll=False, surface=True):
        page = QWidget()
        page.setObjectName("Page")
        shell = QVBoxLayout(page)
        shell.setContentsMargins(0, 0, 0, 0)
        card = QWidget()
        card.setObjectName("Card" if surface else "PageContent")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        shell.addWidget(card, 1)
        layout = QVBoxLayout(card)
        if surface:
            layout.setContentsMargins(32, 26, 32, 26)
        else:
            layout.setContentsMargins(4, 10, 4, 10)
        layout.setSpacing(16)
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
        layout.setContentsMargins(4, 10, 4, 10)
        layout.setSpacing(20)
        self.stack.addWidget(page)
        return layout

    def _build_start_page(self):
        layout = self._card(surface=False)
        _heading(layout, "WALLET IDENTITY", "Name your wallet")
        details = _panel(layout)
        fields = QHBoxLayout()
        fields.setSpacing(24)
        name_column = QVBoxLayout()
        name_column.setSpacing(10)
        caption = _label("Wallet name")
        caption.setObjectName("FieldLabel")
        name_column.addWidget(caption)
        self.wallet_name_input = QLineEdit()
        self.wallet_name_input.setPlaceholderText("Wallet name")
        self.wallet_name_input.returnPressed.connect(self._continue_wallet_setup)
        caption.setBuddy(self.wallet_name_input)
        name_column.addWidget(self.wallet_name_input)
        fields.addLayout(name_column, 2)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(10)
        self.address_type_form = form
        self.address_type = ComboBox()
        for title, code in (
            ("Native SegWit (recommended)", "bech32"),
            ("Taproot (experimental)", "bech32m"),
            ("Nested SegWit (legacy compatibility)", "p2sh-segwit"),
            ("Legacy", "legacy"),
        ):
            self.address_type.addItem(title, code)
        form.addRow("Address type", self.address_type)
        fields.addLayout(form, 1)
        details.addLayout(fields)
        self.multisig_policy_panel = QFrame()
        self.multisig_policy_panel.setObjectName("FormPanel")
        policy_layout = QVBoxLayout(self.multisig_policy_panel)
        policy_layout.setContentsMargins(22, 18, 22, 18)
        policy_layout.setSpacing(10)
        policy_title = _label("Multisig policy")
        policy_title.setObjectName("FormTitle")
        policy_layout.addWidget(policy_title)
        policy_fields = QFormLayout()
        policy_fields.setVerticalSpacing(12)
        policy_fields.setHorizontalSpacing(22)
        self.threshold = QSpinBox()
        self.threshold.setObjectName("PolicyNumber")
        self.threshold.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        self.threshold.setRange(1, 3)
        self.threshold.setValue(2)
        self.threshold.setMinimumWidth(140)
        self.threshold.setMaximumWidth(170)
        self.threshold.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.multisig_total = QSpinBox()
        self.multisig_total.setObjectName("PolicyNumber")
        self.multisig_total.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        self.multisig_total.setRange(2, 20)
        self.multisig_total.setValue(3)
        self.multisig_total.setMinimumWidth(140)
        self.multisig_total.setMaximumWidth(170)
        self.multisig_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        policy_fields.addRow("Required signatures (M)", self.threshold)
        policy_fields.addRow("Total signers (N)", self.multisig_total)
        policy_layout.addLayout(policy_fields)
        self.signer_count_label = _label("2 of 3 signers must approve", True)
        policy_layout.addWidget(self.signer_count_label)
        self.multisig_policy_panel.hide()
        layout.addWidget(self.multisig_policy_panel)
        self.threshold.valueChanged.connect(self._sync_threshold)
        self.multisig_total.valueChanged.connect(self._sync_threshold)
        self._sync_threshold()
        layout.addStretch()
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
        layout = self._card(scroll=True, surface=False)
        _heading(layout, "RECOVERY PHRASE", "Choose your recovery options")
        options = _panel(layout)
        self.audit_details = QWidget()
        audit_layout = QVBoxLayout(self.audit_details)
        audit_layout.setContentsMargins(0, 0, 0, 0)
        audit_layout.setSpacing(10)
        fields = QHBoxLayout()
        fields.setSpacing(24)
        length_column = QVBoxLayout()
        length_column.setSpacing(10)
        length_column.setAlignment(Qt.AlignmentFlag.AlignTop)
        length_caption = _label("Recovery phrase")
        length_caption.setObjectName("FieldLabel")
        length_column.addWidget(length_caption)
        self.word_count = ComboBox()
        for count in (12, 15, 18, 21, 24):
            self.word_count.addItem(f"{count} words" + (" (recommended)" if count == 12 else ""), count)
        length_caption.setBuddy(self.word_count)
        length_column.addWidget(self.word_count)
        length_column.addWidget(_label("12 words: 128 bits · 24 words: 256 bits", True))
        self.word_count.setToolTip("The full SHA-256 is 256 bits. Twelve words use its first 128 bits; 24 words use all 256. BIP39 then derives a 512-bit seed.")
        fields.addLayout(length_column, 1)
        dice_column = QVBoxLayout()
        dice_column.setSpacing(10)
        dice_caption = _label("User entropy · optional")
        dice_caption.setObjectName("FieldLabel")
        dice_column.addWidget(dice_caption)
        self.dice = QLineEdit()
        self.dice.setMaxLength(4096)
        self.dice.setPlaceholderText("Dice rolls, coin flips, or any text")
        dice_caption.setBuddy(self.dice)
        dice_column.addWidget(self.dice)
        self.dice_count = _label("0 bytes entered", True)
        self.dice.textChanged.connect(lambda text: self.dice_count.setText(
            f"{len(text.encode('utf-8'))} bytes entered"
        ))
        dice_column.addWidget(self.dice_count)
        fields.addLayout(dice_column, 3)
        options.addLayout(fields)
        audit_layout.addWidget(_label("Secret · verify on an offline computer only.", True))
        self.entropy_audit = QPlainTextEdit()
        self.entropy_audit.setReadOnly(True)
        self.entropy_audit.setMaximumHeight(250)
        audit_layout.addWidget(self.entropy_audit)
        self.audit_toggle = QPushButton("▸ Audit details")
        self.audit_toggle.setObjectName("Quiet")
        self.audit_toggle.setCheckable(True)
        self.audit_toggle.setToolTip("Show the hashes, secret calculation and reproduction command.")
        self.audit_toggle.toggled.connect(self.audit_details.setVisible)
        self.audit_toggle.toggled.connect(lambda expanded: self.audit_toggle.setText(
            "▾ Audit details" if expanded else "▸ Audit details"
        ))
        options.addWidget(self.audit_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        options.addWidget(self.audit_details)
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
        layout = self._card(scroll=True, surface=False)
        _heading(layout, "WALLET RECOVERY", "Enter your recovery phrase", "Use the words from your existing backup, in order.")
        recovery = _panel(layout)
        self.recovery_count = ComboBox()
        self.recovery_count.setAccessibleName("Recovery phrase length")
        for count in (12, 15, 18, 21, 24):
            self.recovery_count.addItem(f"{count} words", count)
        recovery.addWidget(self.recovery_count, 0, Qt.AlignmentFlag.AlignLeft)
        self.recovery_grid = QGridLayout()
        self.recovery_grid.setHorizontalSpacing(12)
        self.recovery_grid.setVerticalSpacing(10)
        recovery.addLayout(self.recovery_grid)
        self.recovery_hint = _label("", True)
        recovery.addWidget(self.recovery_hint)
        self.final_word = ComboBox()
        self.final_word.hide()
        recovery.addWidget(self.final_word)
        hint = _label("Enter one word in each numbered box. Leave the last box empty if you need to recover its checksum-valid choices.", True)
        recovery.addWidget(hint)
        self.recovery_count.currentIndexChanged.connect(self._render_recovery_fields)
        self._render_recovery_fields()
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

    def _render_recovery_fields(self, *_args):
        previous = [field.text() for field in getattr(self, "recovery_fields", [])]
        _clear_layout(self.recovery_grid)
        count = int(self.recovery_count.currentData())
        columns = 4 if count > 18 else 3
        rows = (count + columns - 1) // columns
        self.recovery_fields = []
        for column in range(4):
            self.recovery_grid.setColumnStretch(column, 0)
        for index in range(count):
            tile = QFrame()
            tile.setObjectName("WordTile")
            line = QHBoxLayout(tile)
            line.setContentsMargins(10, 8, 10, 8)
            line.setSpacing(10)
            number = _label(f"{index + 1:02d}")
            number.setObjectName("WordNumber")
            number.setWordWrap(False)
            number.setFixedWidth(28)
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            line.addWidget(number)
            field = QLineEdit()
            field.setAccessibleName(f"Recovery word {index + 1}")
            field.setPlaceholderText("Recovery word")
            field.setMaxLength(32)
            field.setToolTip(f"Enter word {index + 1} from your recovery phrase.")
            field.textChanged.connect(self._clear_recovery_candidates)
            line.addWidget(field, 1)
            self.recovery_grid.addWidget(tile, index % rows, index // rows)
            self.recovery_fields.append(field)
            if index < len(previous):
                field.setText(previous[index])
        for column in range(columns):
            self.recovery_grid.setColumnStretch(column, 1)

    def _build_phrase_page(self):
        layout = self._card(scroll=True)
        _heading(layout, "YOUR RECOVERY PHRASE", "Write down these words", "Keep them in order. You’ll enter them again to confirm your backup.")
        self.word_grid = QGridLayout()
        self.word_grid.setHorizontalSpacing(12)
        self.word_grid.setVerticalSpacing(10)
        self.word_labels = []
        words_panel = QWidget()
        words_panel.setLayout(self.word_grid)
        self.word_grid.setContentsMargins(0, 8, 0, 8)
        layout.addWidget(words_panel)
        note = _label("Anyone with these words can spend your bitcoin.")
        note.setObjectName("InfoStrip")
        layout.addWidget(note)
        layout.addStretch(1)
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
        layout = self._card(scroll=True)
        _heading(layout, "CHECK YOUR BACKUP", "Confirm your recovery phrase", "Enter every word from your written backup.")
        self.challenge_form = QGridLayout()
        self.challenge_form.setHorizontalSpacing(12)
        self.challenge_form.setVerticalSpacing(10)
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
        layout = self._card(scroll=True, surface=False)
        _heading(layout, "MULTISIG POLICY", "Add your other signers", "Share your public key, then enter each signer’s label, xpub and origin.")
        own_panel = _panel(layout, "Your signer")
        own_key_row = QHBoxLayout()
        own_key_row.setSpacing(24)
        self.multisig_key_qr = QLabel()
        self.multisig_key_qr.setObjectName("QR")
        self.multisig_key_qr.setFixedSize(260, 260)
        self.multisig_key_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        own_key_row.addWidget(self.multisig_key_qr)
        own_key_fields = QVBoxLayout()
        public_caption = _label("Public signer key")
        public_caption.setObjectName("FieldLabel")
        own_key_fields.addWidget(public_caption)
        self.multisig_own_key = QPlainTextEdit()
        self.multisig_own_key.setReadOnly(True)
        self.multisig_own_key.setAccessibleName("Your public signer key")
        self.multisig_own_key.setFixedHeight(130)
        self.multisig_own_key.setFont(fixed_font(10))
        self.multisig_own_key.setToolTip("Share this public account key and its origin with the other signers. It contains no private key.")
        own_key_fields.addWidget(self.multisig_own_key)
        own_key_fields.addStretch()
        own_key_row.addLayout(own_key_fields, 1)
        own_panel.addLayout(own_key_row)
        self.own_signer_name = QLineEdit("This device")
        self.own_signer_name.setPlaceholderText("e.g. Hardware signer")
        self.own_signer_name.setToolTip(
            "A short label for this device in the multisig policy. It does not affect the keys."
        )
        self.multisig_summary = _label(self.signer_count_label.text(), True)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Policy", self.multisig_summary)
        form.addRow("Signer name", self.own_signer_name)
        own_panel.addLayout(form)
        signers_panel = _panel(layout, "Other signers")
        self.signer_grid = QGridLayout()
        self.signer_grid.setHorizontalSpacing(12)
        self.signer_grid.setVerticalSpacing(12)
        self.signer_grid.setColumnStretch(2, 1)
        signers_panel.addLayout(self.signer_grid)
        self.signer_fields = []
        for index in range(2):
            self._add_signer_fields(f"Signer {index + 2}")
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
        workspace_widget = QWidget()
        workspace_widget.setMaximumHeight(600)
        workspace = QHBoxLayout(workspace_widget)
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(24)
        identity = QFrame()
        identity.setObjectName("IdentityHero")
        identity.setMinimumWidth(300)
        identity.setMaximumWidth(340)
        identity_row = QVBoxLayout(identity)
        identity_row.setContentsMargins(28, 30, 28, 30)
        identity_row.setSpacing(24)
        self.identity_badge = _label("Cold signer")
        self.identity_badge.setObjectName("ColdBadge")
        identity_row.addWidget(self.identity_badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.identity_mark = FingerprintMark()
        self.identity_mark.setFixedSize(144, 144)
        self.identity_mark.setToolTip("A visual representation of this signer’s fingerprint. Use the complete wallet policy when checking a multisig wallet.")
        self.identity_mark.installEventFilter(self)
        identity_row.addWidget(self.identity_mark, 0, Qt.AlignmentFlag.AlignLeft)
        identity_copy = QVBoxLayout()
        identity_copy.setSpacing(8)
        self.identity_name = _label("Cold storage", False)
        self.identity_name.setObjectName("IdentityName")
        identity_copy.addWidget(self.identity_name)
        self.identity_policy = _label("Single-signature", True)
        self.identity_policy.setObjectName("IdentityMeta")
        identity_copy.addWidget(self.identity_policy)
        identity_row.addLayout(identity_copy)
        identity_row.addStretch(1)
        fingerprint_column = QVBoxLayout()
        fingerprint_column.setSpacing(10)
        caption = _label("SIGNER FINGERPRINT")
        caption.setObjectName("SectionLabel")
        caption.setWordWrap(False)
        fingerprint_column.addWidget(caption)
        self.identity_fingerprint = _label("Unavailable")
        self.identity_fingerprint.setObjectName("Fingerprint")
        self.identity_fingerprint.setProperty("hero", True)
        self.identity_fingerprint.setFont(fixed_font(18))
        fingerprint_column.addWidget(self.identity_fingerprint)
        identity_row.addLayout(fingerprint_column)
        rule = QFrame()
        rule.setObjectName("IdentityRule")
        rule.setFixedHeight(1)
        identity_row.addWidget(rule)
        change = IconButton("switch", "Change wallet", self._change_wallet)
        change.setToolTip("Save this wallet and choose another saved or new wallet.")
        identity_row.addWidget(change, 0, Qt.AlignmentFlag.AlignLeft)
        workspace.addWidget(identity, 1)

        action_column = QVBoxLayout()
        action_column.setSpacing(18)
        eyebrow = _label("WALLET WORKSPACE")
        eyebrow.setObjectName("SectionLabel")
        eyebrow.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_column.addWidget(eyebrow)
        heading = _label("Choose an action", False)
        heading.setObjectName("HeroTitle")
        heading.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_column.addWidget(heading)
        scan = ActionRow(
            "▦", "Scan QR", "Verify an address or sign a transaction", primary=True, hero=True,
            tooltip="Verify a receive address or review a PSBT before signing.",
        )
        scan.clicked.connect(lambda: self.stack.setCurrentIndex(9))
        scan.setMaximumHeight(240)
        addresses = ActionRow(
            "▣", "Wallet addresses", "View your addresses and labels",
            tooltip="See saved addresses and labels generated or confirmed by this signer.",
        )
        addresses.clicked.connect(self._open_addresses)
        tools = ActionRow(
            "⚙", "Tools & Settings", "Wallet policy, exports and preferences",
            tooltip="Export the watch-only wallet, view the policy, or change settings.",
        )
        tools.clicked.connect(lambda: self.stack.setCurrentIndex(12))
        secondary = QVBoxLayout()
        secondary.setSpacing(16)
        secondary.addWidget(addresses, 1)
        secondary.addWidget(tools, 1)
        action_column.addWidget(scan, 1)
        action_column.addLayout(secondary)
        workspace.addLayout(action_column, 3)
        layout.addWidget(workspace_widget, 1)
        layout.addStretch()

    def _build_scan_page(self):
        layout = self._card()
        self._add_back_heading(layout, "Scan QR code", "", 6)
        self.scan_target = QFrame()
        self.scan_target.setObjectName("ScanTarget")
        self.scan_target.setMinimumHeight(190)
        scan_layout = QHBoxLayout(self.scan_target)
        scan_layout.setContentsMargins(28, 24, 28, 24)
        scan_copy = QVBoxLayout()
        scan_copy.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        scan_copy.setSpacing(10)
        scan_ready = _label("Ready to scan")
        scan_ready.setObjectName("Heading")
        scan_copy.addWidget(scan_ready)
        scan_copy.addWidget(_label("Receiving address or unsigned transaction", True))
        scan_layout.addLayout(scan_copy, 1)
        artwork = ScanIllustration()
        artwork.setFixedSize(140, 140)
        scan_layout.addWidget(artwork)
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
        self.address_table = EmptyTable(0, 3, empty_title="No saved addresses", empty_hint="Generate an address or verify one from your online node.")
        self.address_table.setHorizontalHeaderLabels(["LABEL", "ADDRESS", "USED"])
        self.address_table.verticalHeader().hide()
        self.address_table.verticalHeader().setDefaultSectionSize(48)
        self.address_table.setAlternatingRowColors(True)
        self.address_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.address_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.address_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.address_table.setShowGrid(False)
        self.address_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.address_table.setColumnWidth(0, 220)
        self.address_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.address_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.address_table.setColumnWidth(2, 84)
        self.address_table.cellActivated.connect(self._open_address_from_row)
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
        detail.setSpacing(28)
        self.address_qr = QLabel()
        self.address_qr.setObjectName("QR")
        self.address_qr.setFixedSize(320, 320)
        self.address_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail.addWidget(self.address_qr, 0, Qt.AlignmentFlag.AlignTop)
        fields = QVBoxLayout()
        address_caption = _label("RECEIVING ADDRESS")
        address_caption.setObjectName("SectionLabel")
        fields.addWidget(address_caption)
        self.address_detail_value = QLineEdit()
        self.address_detail_value.setReadOnly(True)
        self.address_detail_value.setFont(fixed_font(9))
        fields.addWidget(self.address_detail_value)
        label_caption = _label("LABEL · OPTIONAL")
        label_caption.setObjectName("SectionLabel")
        fields.addWidget(label_caption)
        self.address_detail_label = QLineEdit()
        self.address_detail_label.setPlaceholderText("e.g. Long-term savings")
        fields.addWidget(self.address_detail_label)
        self.address_used_status = _label("Saved on this signer", True)
        fields.addWidget(self.address_used_status)
        self.address_used_check = QCheckBox("Mark as used")
        self.address_used_check.setToolTip("Newly generated addresses start marked used. This is a tracking label; the offline signer cannot check blockchain activity.")
        self.address_used_check.setStyleSheet("QCheckBox::indicator { width: 22px; height: 22px; }")
        fields.addWidget(self.address_used_check)
        fields.addStretch()
        detail.addLayout(fields, 1)
        layout.addLayout(detail)
        layout.addStretch()
        done = QPushButton("Done")
        done.setObjectName("Primary")
        done.clicked.connect(self._save_address_detail)
        footer = QHBoxLayout()
        remove = QPushButton("Remove address")
        remove.clicked.connect(self._remove_address)
        footer.addWidget(remove)
        footer.addStretch()
        footer.addWidget(done)
        layout.addLayout(footer)

    def _build_tools_page(self):
        layout = self._card()
        self._add_back_heading(layout, "Tools & Settings", "Wallet policy, exports, and preferences.", 6)
        actions = QVBoxLayout()
        actions.setSpacing(9)
        policy = ActionRow("⌘", "Wallet info", "", tooltip="Review the wallet identity, signer keys, and public descriptors.")
        policy.clicked.connect(lambda: self.stack.setCurrentIndex(13))
        export = ActionRow(
            "⇧", "Export watch-only wallet", "",
            tooltip="Export public wallet data for use on the online node.", icon_key="export",
        )
        export.clicked.connect(self._export_watchonly_wallet)
        settings = ActionRow("⚙", "Settings", "", tooltip="Change appearance and view cold-signer session details.")
        settings.clicked.connect(self._open_settings)
        for action in (policy, export, settings):
            actions.addWidget(action)
        layout.addLayout(actions)
        layout.addStretch()

    def _build_policy_page(self):
        layout = self._card(scroll=True, surface=False)
        self._add_back_heading(layout, "Wallet info", "Public wallet data supplied and checked by Bitcoin Core.", 12)
        self.policy_identity = _label("")
        self.policy_identity.setObjectName("Value")
        identity = _panel(layout, "Wallet identity")
        identity.addWidget(self.policy_identity)
        signers = _panel(layout, "Signers")
        self.signers_panel = signers.parentWidget()
        self.signer_map = QPlainTextEdit()
        self.signer_map.setReadOnly(True)
        self.signer_map.setAccessibleName("Wallet signers")
        self.signer_map.setToolTip("The wallet’s signers and this signer’s public account key. Keep the complete public wallet policy for multisig recovery.")
        self.signer_map.setFont(fixed_font(11))
        self.signer_map.setFixedHeight(125)
        signers.addWidget(self.signer_map)
        descriptors = _panel(layout, "Public descriptors")
        self.descriptors = QPlainTextEdit()
        self.descriptors.setReadOnly(True)
        self.descriptors.setAccessibleName("Public descriptors")
        self.descriptors.setFont(fixed_font(11))
        self.descriptors.setMinimumHeight(150)
        descriptors.addWidget(self.descriptors)
        show_qr = QPushButton("Show as QR")
        show_qr.clicked.connect(self._export_watchonly_wallet)
        descriptors.addWidget(show_qr, 0, Qt.AlignmentFlag.AlignLeft)

    def _build_settings_page(self):
        layout = self._card(surface=False)
        self._add_back_heading(layout, "Settings", "", 12)
        appearance_panel = _panel(layout)
        appearance = QHBoxLayout()
        heading = _label("Appearance")
        heading.setObjectName("FormTitle")
        appearance.addWidget(heading)
        appearance.addStretch()
        self.settings_theme_button = IconButton("dark", "Dark mode", self._toggle_theme)
        appearance.addWidget(self.settings_theme_button)
        appearance_panel.addLayout(appearance)
        session = _panel(layout, "Cold signer mode enabled")
        self.session_details = _label(
            "Swap and Core peer networking are disabled. Host networking stays on in development mode."
            if self.dev_keep_network else "Permanent offline policy is enforced across sessions and reboots. Swap is disabled while signing.", True
        )
        session.addWidget(self.session_details)
        warning = _label("Never take a real-wallet computer back online. For the strongest safeguard, remove Wi-Fi, Ethernet, Bluetooth and other networking hardware.")
        warning.setObjectName("InfoStrip")
        session.addWidget(warning)
        advanced = QCheckBox("Enable BIP39 passphrases (advanced)")
        advanced.setToolTip("Adds an optional BIP39 passphrase to setup and recovery. Each passphrase creates a different wallet; wallet-file encryption is separate.")
        advanced.setChecked(QSettings("CoreCompanion", "CoreCompanion").value("bip39_enabled", False, type=bool))
        advanced.toggled.connect(self._set_advanced_bip39)
        session.addWidget(advanced)
        session.addWidget(_label("Wallet files are saved on this computer. Encryption is optional; labels and public descriptors remain readable.", True))
        layout.addStretch()

    def _build_setup_page(self):
        layout = self._page()
        _heading(layout, "GET STARTED", "Wallet setup")
        saved = QHBoxLayout()
        saved.addWidget(_label("Saved wallets"))
        self.saved_wallets = ComboBox()
        self.saved_wallets.setToolTip("Open a saved wallet. Its encryption status is shown in the list.")
        saved.addWidget(self.saved_wallets, 1)
        self.open_saved_button = QPushButton("Open wallet")
        self.open_saved_button.clicked.connect(self._open_saved_wallet)
        saved.addWidget(self.open_saved_button)
        layout.addLayout(saved)
        choices = QHBoxLayout()
        choices.setSpacing(20)
        self.create_choice = ChoiceRow("new", "Create a new wallet", accent="blue", card=True,
                                       tooltip="Generate a new BIP39 recovery phrase for this cold signer.")
        self.create_choice.clicked.connect(lambda: self._choose_setup("new"))
        self.recover_choice = ChoiceRow("import", "Recover from phrase", accent="blue", card=True,
                                        tooltip="Recover a wallet from your existing English BIP39 recovery phrase.")
        self.recover_choice.clicked.connect(lambda: self._choose_setup("recover"))
        choices.addWidget(self.create_choice)
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
        _heading(layout, "SIGNING POLICY", "Choose wallet type")
        choices = QHBoxLayout()
        choices.setSpacing(20)
        self.single_choice = ChoiceRow(
            "key", "Single signature", accent="blue", card=True,
            tooltip="One private key controls this wallet. Keep its recovery phrase as your backup."
        )
        self.single_choice.clicked.connect(lambda: self._choose_type("single"))
        self.multi_choice = ChoiceRow(
            "multisig", "Multisig", accent="blue", card=True,
            tooltip="Several signers share a wallet. Choose how many signatures are required and add each signer’s public key and origin."
        )
        self.multi_choice.clicked.connect(lambda: self._choose_type("multisig"))
        choices.addWidget(self.single_choice)
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

    def _build_protection_page(self):
        layout = self._card(scroll=True, surface=False)
        _heading(layout, "WALLET PROTECTION", "Protect your wallet")
        columns = QHBoxLayout()
        columns.setSpacing(20)
        content = _panel(columns, "Recovery protection", "A BIP39 passphrase creates a different wallet.")
        self.bip39_panel = content.parentWidget()
        self.bip39_panel.setVisible(QSettings("CoreCompanion", "CoreCompanion").value("bip39_enabled", False, type=bool))
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

        content.addStretch()
        content = _panel(columns, "Wallet-file encryption", "Optional · choose before Core creates the wallet keys")
        self.encrypt_wallet = QCheckBox("Encrypt wallet file (optional)")
        self.encrypt_wallet.setToolTip("Optional. Core encrypts the saved private keys, and you will need this password to reopen or sign. If disabled, the saved wallet file contains unencrypted private keys.")
        self.encrypt_wallet.setChecked(False)
        content.addWidget(self.encrypt_wallet)
        self.wallet_storage_note = _label("", True)
        self.wallet_storage_note.setObjectName("InfoStrip")
        content.addWidget(self.wallet_storage_note)
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
        self._toggle_wallet_fields(self.encrypt_wallet.isChecked())
        content.addStretch()
        layout.addLayout(columns)
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
        self.multisig_policy_panel.setVisible(self.type_choice == "multisig")
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
        pass  # Navigation stays in the fixed header.

    def _add_back_heading(self, layout, title, description, target):
        heading = _label(title)
        heading.setObjectName("Title")
        layout.addWidget(heading)
        if description:
            layout.addWidget(_label(description, True))

    def _install_help_targets(self):
        fields = {
            self.wallet_name_input: "A name for this wallet in the interface and public backup. It does not change the keys.",
            self.address_type: "Choose the address format. Keep this choice with your recovery backup to recreate the same wallet.",
            self.dice: "Optional dice rolls, coin flips or arbitrary text. Exact UTF-8 bytes, including spaces, are mixed with OS randomness and the wallet-file hash.",
            self.word_count: "12 words encode 128 bits; 24 encode 256 bits. The full SHA-256 is always shown in Audit details. BIP39 later derives a 512-bit seed.",
            self.entropy_audit: "Secret source values, the exact SHA-256 command, and the resulting entropy. These values can recreate your recovery phrase.",
            self.recovery_count: "Choose the number of words on your existing recovery backup.",
            self.final_word: "Choose the final word from your backup. Several words can pass the checksum; only your original word restores the intended wallet.",
            self.threshold: "M: the number of different signers required to authorize a transaction.",
            self.multisig_total: "N: the total number of signers in this wallet, including this signer.",
            self.own_signer_name: "A short name for this device in the multisig wallet policy.",
            self.address_detail_value: "The complete receiving address generated or checked by Bitcoin Core. Compare every character when verifying it elsewhere.",
            self.address_detail_label: "An optional label saved with your Core wallet. Wallet-file encryption is optional.",
            self.descriptors: "Public receive and change descriptors checked by Core. Multisig recovery needs this policy as well as the required private keys.",
            self.bip39_passphrase1: "An extra secret used with the recovery phrase. A different passphrase produces a different wallet; there is no wrong-passphrase warning.",
            self.bip39_passphrase2: "Enter the BIP39 passphrase again to check for typing mistakes.",
            self.encrypt_wallet: "Optional. When enabled, Core encrypts the saved private keys and requires this password to reopen or sign. When disabled, anyone with access to the wallet file can use its private keys.",
            self.wallet_password1: "Password for the saved Core wallet file. Required only when wallet-file encryption is enabled; separate from a BIP39 passphrase.",
            self.wallet_password2: "Enter the wallet-file password again to check for typing mistakes.",
            self.scan_payload: "Paste a Bitcoin address, payment QR text, or base64 PSBT. Continue detects which type it is.",
            self.psbt_input: "A partially signed Bitcoin transaction from your online wallet. Core reviews its contents before signing is enabled.",
            self.psbt_review: "Check every recipient, amount, fee, and change output. The offline signer cannot check these against a local blockchain.",
            self.signer_password: "The saved Core wallet encryption password. It is cleared from this field after each signing attempt.",
            self.signed_psbt: "The transaction with this signer’s signatures. Transfer it to the other signers or your online wallet; it has not been broadcast.",
            self.verify_address_input: "Enter a Bitcoin address or bitcoin: payment URI. Core checks whether the address belongs to this wallet.",
            self.verified_address_label: "An optional label saved after Core verifies the address.",
            self.theme_button: "Switch between light and dark appearance.",
            self.settings_theme_button: "Switch between light and dark appearance.",
            self.create_choice: "Create a new recovery phrase for this signer.",
            self.recover_choice: "Restore a signer using an existing BIP39 recovery phrase and any BIP39 passphrase.",
            self.single_choice: "One private key is enough to sign for this wallet.",
            self.multi_choice: "Several signers share a wallet. You choose how many signatures a transaction needs.",
            self.bip39_show: "Show or hide the BIP39 passphrase while you enter it.",
            self.wallet_show: "Show or hide the wallet-file encryption password while you enter it.",
            self.show_signer_password: "Show or hide the wallet password before signing.",
            self.address_table: "Open an address to view its QR, edit its saved label, mark it used or remove it from this list.",
        }
        for widget, explanation in fields.items():
            widget.setToolTip(explanation)
        for index, widget in enumerate(self.recovery_fields, 1):
            widget.setToolTip(f"Enter word {index} from your existing recovery phrase. The offline signer checks the BIP39 checksum.")
        descriptions = {
            "Generate recovery phrase": "Generate a recovery phrase from Bitcoin Core wallet data, Linux randomness, and optional user entropy.",
            "Generate address": "Ask Core for a fresh receiving address and save its derivation index and label.",
            "I wrote it down": "Hide the phrase and check that you can retype every word from your backup.",
            "Skip confirmation (testing)": "Development only: continue without checking your written recovery phrase. Use test wallets only.",
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
        heading = QHBoxLayout()
        heading_copy = QVBoxLayout()
        _heading(heading_copy, "TRANSACTION SIGNING", "Review, then sign", "Check every address and amount before signing.")
        heading.addLayout(heading_copy, 1)
        back = IconButton("back", "Back to wallet", lambda: self.stack.setCurrentIndex(6))
        heading.addWidget(back, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)

        self.psbt_import_panel = QFrame()
        self.psbt_import_panel.setObjectName("SubtlePanel")
        import_layout = QVBoxLayout(self.psbt_import_panel)
        import_layout.setContentsMargins(20, 18, 20, 18)
        import_layout.setSpacing(12)
        import_title = _label("Import an unsigned transaction")
        import_title.setObjectName("Heading")
        import_layout.addWidget(import_title)
        self.psbt_input = QPlainTextEdit()
        self.psbt_input.setPlaceholderText("Paste a PSBT, scan a QR code, or choose a file")
        self.psbt_input.setFixedHeight(88)
        self.psbt_input.textChanged.connect(self._invalidate_psbt_review)
        import_layout.addWidget(self.psbt_input)
        controls = QHBoxLayout()
        scan = IconButton("scan", "Scan QR", lambda: self._start_qr_scanner(),
                          tooltip="Open the camera to import an unsigned transaction from a QR code.")
        controls.addWidget(scan)
        load = IconButton("file", "Choose file…", self._load_psbt_file,
                          tooltip="Import a binary or base64 PSBT file for Core to review.")
        controls.addWidget(load)
        controls.addStretch()
        review = QPushButton("Review transaction")
        review.setObjectName("Primary")
        review.clicked.connect(self._review_psbt)
        controls.addWidget(review)
        import_layout.addLayout(controls)
        layout.addWidget(self.psbt_import_panel)

        self.review_panel = QWidget()
        self.review_layout = QVBoxLayout(self.review_panel)
        self.review_layout.setContentsMargins(0, 0, 0, 0)
        self.review_layout.setSpacing(12)
        layout.addWidget(self.review_panel)
        self.review_panel.hide()

        detail_controls = QHBoxLayout()
        self.review_details_toggle = QPushButton("Show Core details")
        self.review_details_toggle.setObjectName("Quiet")
        self.review_details_toggle.setCheckable(True)
        self.review_details_toggle.setToolTip("Show Core’s complete review, including every output, the transaction identifier, fee, and locktime.")
        self.review_details_toggle.hide()
        detail_controls.addWidget(self.review_details_toggle)
        detail_controls.addStretch()
        self.replace_psbt_button = IconButton("refresh", "Replace transaction", self._replace_transaction,
                                             tooltip="Discard this review and import or review a transaction again before signing.")
        self.replace_psbt_button.hide()
        detail_controls.addWidget(self.replace_psbt_button)
        layout.addLayout(detail_controls)
        self.psbt_review = QPlainTextEdit()
        self.psbt_review.setReadOnly(True)
        self.psbt_review.setFixedHeight(190)
        self.psbt_review.setFont(fixed_font(10))
        self.psbt_review.hide()
        self.review_details_toggle.toggled.connect(self.psbt_review.setVisible)
        layout.addWidget(self.psbt_review)

        self.authorize_panel = QFrame()
        self.authorize_panel.setObjectName("SubtlePanel")
        authorize = QVBoxLayout(self.authorize_panel)
        authorize.setContentsMargins(20, 16, 20, 16)
        authorize.setSpacing(12)
        caution = _label("Amounts and fees come from the PSBT. This offline signer cannot verify them against the blockchain.")
        caution.setObjectName("FooterNote")
        authorize.addWidget(caution)
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
        authorize.addLayout(password_row)
        sign_row = QHBoxLayout()
        sign_note = _label("Signing does not broadcast this transaction.")
        sign_note.setObjectName("FooterNote")
        sign_row.addWidget(sign_note, 1)
        self.sign_button = QPushButton("Sign reviewed transaction")
        self.sign_button.setObjectName("Primary")
        self.sign_button.setEnabled(False)
        self.sign_button.clicked.connect(self._sign_reviewed_psbt)
        sign_row.addWidget(self.sign_button)
        authorize.addLayout(sign_row)
        layout.addWidget(self.authorize_panel)
        self.authorize_panel.hide()

        self.signed_panel = QFrame()
        self.signed_panel.setObjectName("SubtlePanel")
        signed_layout = QVBoxLayout(self.signed_panel)
        signed_layout.setContentsMargins(20, 18, 20, 18)
        signed_title = _label("Signature added")
        signed_title.setObjectName("Heading")
        signed_layout.addWidget(signed_title)
        signed_row = QHBoxLayout()
        self.signed_qr = QLabel()
        self.signed_qr.setFixedSize(320, 320)
        self.signed_qr.setObjectName("QR")
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
        signed_layout.addLayout(signed_row)
        layout.addWidget(self.signed_panel)
        self.signed_panel.hide()
        layout.addStretch()

    def _replace_transaction(self):
        self._invalidate_psbt_review()
        self.psbt_import_panel.show()
        self.psbt_input.setFocus()

    def _render_transaction_review(self, review):
        """Present every Core-reviewed output without shortening addresses or scripts."""
        _clear_layout(self.review_layout)
        summary = QFrame()
        summary.setObjectName("SubtlePanel")
        metrics = QHBoxLayout(summary)
        metrics.setContentsMargins(20, 16, 20, 16)
        fee = review["fee"]
        for caption, value in (
            ("OUTPUTS", str(len(review["outputs"]))),
            ("NETWORK FEE", f"{Decimal(str(fee)):.8f} BTC" if fee is not None else "Unavailable"),
            ("INPUTS", str(review["inputs"])),
        ):
            column = QVBoxLayout()
            label = _label(caption)
            label.setObjectName("SectionLabel")
            column.addWidget(label)
            amount = _label(value)
            amount.setObjectName("KPIValue")
            column.addWidget(amount)
            metrics.addLayout(column, 1)
        self.review_layout.addWidget(summary)
        # Keep untrusted PSBTs from creating an unbounded number of widgets.
        # Larger reviews use the complete text view, with every output intact.
        outputs = review["outputs"]
        structured = len(outputs) <= 24 and all(
            len(output["address"]) <= 256 and len(output["script"]) <= 512 for output in outputs
        )
        if not structured:
            note = _label("This transaction needs the detailed view. Review every output in Core details below.")
            note.setObjectName("InfoStrip")
            self.review_layout.addWidget(note)
        for index, output in enumerate(outputs if structured else (), 1):
            card = QFrame()
            card.setObjectName("Surface")
            content = QVBoxLayout(card)
            content.setContentsMargins(20, 16, 20, 16)
            content.setSpacing(8)
            line = QHBoxLayout()
            number = _label(f"{index:02d}")
            number.setObjectName("OutputIndex")
            number.setWordWrap(False)
            line.addWidget(number)
            role, kind = ("Change · Core verified", "change") if output["is_change"] else (
                ("Own address", "own") if output["is_mine"] else ("Recipient · verify address", "recipient")
            )
            caption = _label(role)
            caption.setObjectName("OutputRole")
            caption.setWordWrap(False)
            caption.setProperty("kind", kind)
            line.addWidget(caption)
            line.addStretch()
            value = output["amount"]
            amount = _label(f"{Decimal(str(value)):.8f} BTC" if value is not None else "Amount unavailable")
            amount.setObjectName("OutputAmount")
            amount.setWordWrap(False)
            line.addWidget(amount)
            content.addLayout(line)
            address = _label(output["address"])
            address.setObjectName("ReviewAddress")
            address.setFont(fixed_font(11))
            address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            content.addWidget(address)
            if output["address"].startswith("(non-standard"):
                script = _label(output["script"])
                script.setFont(fixed_font(10))
                script.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                content.addWidget(script)
            self.review_layout.addWidget(card)
        states = review.get("analysis", {}).get("inputs", [])
        missing = sum(item.get("has_utxo") is not True for item in states)
        if missing:
            warning = _label(f"Core could not verify UTXO details for {missing} input(s).")
            warning.setObjectName("ReviewWarning")
            self.review_layout.addWidget(warning)
        self.review_panel.show()
        self.psbt_import_panel.hide()
        self.review_details_toggle.show()
        self.review_details_toggle.setChecked(not structured)
        self.psbt_review.setFixedHeight(190 if structured else 320)
        self.replace_psbt_button.show()
        self.authorize_panel.show()
        self.signer_password.setVisible(self.wallet_encrypted)
        self.show_signer_password.setVisible(self.wallet_encrypted)

    def _build_verify_address_page(self):
        layout = self._card(surface=False)
        self._add_back_heading(layout, "Verify a receiving address", "", 9)
        address_panel = _panel(layout, "Receiving address")
        self.verify_address_input = QLineEdit()
        self.verify_address_input.setPlaceholderText("Bitcoin address or bitcoin: URI")
        self.verify_address_input.setFont(fixed_font(11))
        self.verify_address_input.textChanged.connect(self._clear_address_result)
        address_panel.addWidget(self.verify_address_input)
        controls = QHBoxLayout()
        scan = IconButton("scan", "Scan QR", lambda: self._start_qr_scanner(self.verify_address_input),
                          tooltip="Use the camera to read a Bitcoin receiving address.")
        controls.addWidget(scan)
        verify = QPushButton("Verify address")
        verify.setObjectName("Primary")
        verify.clicked.connect(self._verify_receive_address)
        controls.addWidget(verify)
        controls.addStretch()
        address_panel.addLayout(controls)
        self.verify_result = _label("")
        self.verify_result.setObjectName("Verification")
        self.verify_result.setMinimumHeight(56)
        self.verify_result.hide()
        layout.addWidget(self.verify_result)
        label_panel = _panel(layout, "Label", "Optional · saved with this address on the signer.")
        self.verified_address_label = QLineEdit()
        self.verified_address_label.setPlaceholderText("Label · optional")
        self.verified_address_label.setEnabled(False)
        label_panel.addWidget(self.verified_address_label)
        layout.addStretch()
        footer = QHBoxLayout()
        back = QPushButton("Back to wallet")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(9))
        footer.addWidget(back)
        footer.addStretch()
        self.verify_done = QPushButton("Done")
        self.verify_done.setObjectName("Primary")
        self.verify_done.setEnabled(False)
        self.verify_done.clicked.connect(self._save_verified_address)
        footer.addWidget(self.verify_done)
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
            self.wallet_storage_note.setText(
                "Without encryption, the saved file contains usable private keys. Use full-disk encryption and protect this computer physically."
            )
        else:
            self.wallet_storage_note.setText(
                "Core encrypts the saved file. Keep this password with your recovery backup; it is needed to reopen or sign."
            )

    def _toggle_wallet_visibility(self, visible):
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.wallet_password1.setEchoMode(mode)
        self.wallet_password2.setEchoMode(mode)

    def _read_protection_options(self):
        bip39_passphrase = ""
        wallet_password = ""
        if self.bip39_panel.isVisible() and self.use_bip39_passphrase.isChecked():
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
        for field in self.recovery_fields:
            field.clear()
        self.stack.setCurrentIndex(2)

    def _open_core(self, bitcoind):
        try:
            self.core = OfflineCore(bitcoind, self.session_id, dev_keep_network=self.dev_keep_network).start()
        except (ColdSetupError, OSError) as exc:
            # Startup errors are reported by the parent shell. This helper is
            # still hidden, so opening a dialog here would create a second
            # visible window before the handoff.
            self.startup_error = " ".join(str(exc).split())[:1600]
            self.reject()

    def _update_entropy_audit(self, *_args):
        if self.wallet_digest is None or self.os_entropy is None:
            self.entropy_audit.clear()
            return
        user = self.dice.text()
        size = int(self.word_count.currentData()) * 4 // 3
        try:
            material = entropy_material(self.wallet_digest, self.os_entropy, user)
        except SeedError as exc:
            self.entropy_audit.setPlainText(str(exc))
            return
        digest = hashlib.sha256(material).digest()
        # Hex-only literals make this command safe to paste with arbitrary user text.
        command = ('python3 -c "from hashlib import sha256; '
                   f"wallet=bytes.fromhex('{self.wallet_digest.hex()}'); "
                   f"rng=bytes.fromhex('{self.os_entropy.hex()}'); "
                   f"user=bytes.fromhex('{user.encode('utf-8').hex()}'); "
                   "data=(b'Core Companion BIP39 entropy v2\\x00'"
                   "+len(wallet).to_bytes(2,'big')+wallet"
                   "+len(rng).to_bytes(2,'big')+rng"
                   "+len(user).to_bytes(4,'big')+user); print(sha256(data).hexdigest())" + '"')
        self.entropy_audit.setPlainText(
            f"OS RNG (hex): {self.os_entropy.hex()}\n"
            f"Wallet.dat SHA-256: {self.wallet_digest.hex()}\n"
            f"User entropy (UTF-8 hex): {user.encode('utf-8').hex() or '(none)'}\n\n"
            f"Reproduce SHA-256:\n{command}\n\n"
            f"Full SHA-256 (256 bits): {digest.hex()}\n"
            f"BIP39 phrase entropy ({size * 8} bits, first {size} bytes): {digest[:size].hex()}"
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
            QMessageBox.warning(self, "Check user entropy", str(exc))
            return
        self.words = self.phrase.split()
        self.phrase_source = "create"
        self._render_words()
        self.stack.setCurrentIndex(3)

    def _render_words(self):
        _clear_layout(self.word_grid)
        self.word_labels = []
        columns = 4 if len(self.words) > 18 else 3
        rows = (len(self.words) + columns - 1) // columns
        for index, word in enumerate(self.words):
            tile = QFrame()
            tile.setObjectName("WordTile")
            line = QHBoxLayout(tile)
            line.setContentsMargins(14, 10, 14, 10)
            line.setSpacing(14)
            number = _label(f"{index + 1:02d}")
            number.setObjectName("WordNumber")
            number.setWordWrap(False)
            number.setFixedWidth(28)
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            line.addWidget(number)
            item = _label(word)
            item.setObjectName("WordText")
            item.setWordWrap(False)
            item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            line.addWidget(item, 1)
            self.word_grid.addWidget(tile, index % rows, index // rows)
            self.word_labels.append(item)

    def _clear_recovery_candidates(self):
        self.recovery_prefix = None
        self.recovery_hint.clear()
        self.final_word.clear()
        self.final_word.hide()

    def _continue_recovery(self):
        count = int(self.recovery_count.currentData())
        tokens = [field.text().strip() for field in self.recovery_fields]
        if any(len(value.split()) > 1 for value in tokens):
            QMessageBox.warning(self, "One word per box", "Enter one recovery word in each numbered box.")
            return
        missing = [index for index, value in enumerate(tokens) if not value]
        if not missing:
            try:
                self.phrase = validate_phrase(" ".join(tokens))
            except SeedError as exc:
                QMessageBox.warning(self, "Phrase checksum failed", str(exc))
                return
        elif missing == [count - 1] and all(tokens[:-1]):
            prefix = " ".join(tokens[:-1])
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
                self.final_word.setCurrentIndex(-1)
                self.final_word.show()
                self.recovery_prefix = prefix
                self.recovery_hint.setText(
                    f"{len(candidates)} checksum-valid final words. Choose the final word from your backup, then continue again."
                )
                return
            final = self.final_word.currentText()
            if not final:
                QMessageBox.warning(self, "Choose the final word", "Choose the final word from your existing backup.")
                return
            self.phrase = validate_phrase(prefix + " " + final)
        else:
            QMessageBox.warning(
                self,
                "Recovery phrase length",
                f"Fill all {count} numbered boxes in order, or leave only word {count} empty to see valid final-word choices.",
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
            columns = 4 if len(self.words) > 18 else 3
            rows = (len(self.words) + columns - 1) // columns
            self.challenge_form.addWidget(field, index % rows, index // rows)
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
        key.setPlaceholderText("[fingerprint/path]xpub…")
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
            (key, "The signer’s xpub with its actual fingerprint and origin path. BIP48, BIP87 and custom paths are accepted."),
            (scan, "Scan this signer’s public account key QR."),
        ):
            widget.setToolTip(tip)
            widget.installEventFilter(self)
        self._sync_threshold()

    def _sync_threshold(self, *_args):
        total = self.multisig_total.value()
        self.threshold.setMaximum(total)
        summary = f"{self.threshold.value()} of {total} signers must approve"
        self.signer_count_label.setText(summary)
        if hasattr(self, "multisig_summary"):
            self.multisig_summary.setText(summary)

    def _sync_multisig_signer_fields(self):
        desired = self.multisig_total.value() - 1
        while len(self.signer_fields) > desired:
            name, key, scan = self.signer_fields.pop()
            row = len(self.signer_fields)
            for widget in (name, key, scan):
                self.signer_grid.removeWidget(widget)
                widget.deleteLater()
            label_item = self.signer_grid.itemAtPosition(row, 0)
            if label_item and label_item.widget():
                label_item.widget().deleteLater()
        while len(self.signer_fields) < desired:
            self._add_signer_fields(f"Signer {len(self.signer_fields) + 2}")
        self._sync_threshold()

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
                QMessageBox.warning(self, "Complete signer details", "Enter a label and xpub with origin information for every other signer.")
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
        self._show_complete(result, f"{self.threshold.value()} of {len(signers) + 1} multisig")

    def _prepare_multisig(self):
        self._sync_multisig_signer_fields()
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
        for field in self.recovery_fields:
            field.clear()
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
        self.descriptors.setPlainText(self.core.public_descriptor(result["descriptors"]))
        self.wallet_display_name = self.wallet_name_input.text().strip() or "Cold signer"
        self.setWindowTitle(f"Core Companion — {self.wallet_display_name}")
        self.wallet_fingerprint = str(result.get("address_info", {}).get("hdmasterfingerprint", "")).upper()
        own_key = result.get("own_account_key", "")
        if not self.wallet_fingerprint and own_key.startswith("[") and "/" in own_key:
            self.wallet_fingerprint = own_key[1:9].upper()
        self.identity_name.setText(self.wallet_display_name)
        self.identity_policy.setText(wallet_type)
        self.identity_fingerprint.setText(
            self.wallet_fingerprint if self.wallet_fingerprint else "Unavailable"
        )
        self.policy_identity.setText(
            f"{self.wallet_display_name}  ·  {wallet_type}\n"
            + (f"Signer fingerprint · {self.wallet_fingerprint}" if self.wallet_fingerprint else "Signer fingerprint unavailable from Core")
        )
        self.status_left.setText(f"{self.wallet_display_name} · {wallet_type}")
        self.status_right.setText("Encrypted wallet file" if self.wallet_encrypted else "Unencrypted wallet file")
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
            signer_text += "\n\nYour public account key\n" + own_key
        self.signer_map.setPlainText(signer_text)
        self.wallet_type_summary = wallet_type
        self.signers_panel.setVisible(bool(result.get("signers")))
        self.wallet_result = result
        self._persist_current_wallet()
        self.stack.setCurrentIndex(6)

    def _update_identity_mark(self):
        self.identity_mark.set_identity(self.descriptors.toPlainText().split("#", 1)[0])

    def _change_wallet(self):
        try:
            if not self._persist_current_wallet():
                return
            self.core.unload_signer()
        except (ColdSetupError, CoreError) as exc:
            QMessageBox.critical(self, "Could not save wallet", str(exc))
            return
        self.wallet_ready = self.multisig_prepared = False
        self.setWindowTitle("Core Companion — Cold storage")
        self.status_left.setText("Cold signer · choose wallet")
        self.status_right.setText("Wallet-file encryption is optional")
        self._clear_setup_secrets()
        self.address_records = []
        self.hidden_addresses = []
        self.wallet_name_input.clear()
        self.setup_choice = self.type_choice = None
        self.threshold.setValue(2)
        self.multisig_total.setValue(3)
        self._sync_threshold()
        self.multisig_policy_panel.hide()
        for control in (self.create_choice, self.recover_choice, self.single_choice, self.multi_choice):
            control.setChecked(False)
        self.setup_continue.setEnabled(False)
        self.type_continue.setEnabled(False)
        self._refresh_saved_wallets()
        self.stack.setCurrentIndex(15)

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

    def keyPressEvent(self, event):
        # Enter activates the focused button, never an unrelated dialog default.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = self.focusWidget()
            if isinstance(focused, QPushButton) and focused.isEnabled() and not event.isAutoRepeat():
                focused.click()
            event.accept()
            return
        super().keyPressEvent(event)

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
            used_item.setToolTip("Tracking label on this signer; not an on-chain balance check.")
            used_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = used_item.font()
            font.setPointSize(18)
            font.setBold(True)
            used_item.setFont(font)
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
        self._persist_current_wallet()
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
        self.address_used_status.setText("Used" if record.get("used") else "Unused · not marked used")
        self.address_used_check.setChecked(bool(record.get("used")))
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
        record["used"] = self.address_used_check.isChecked()
        self._persist_current_wallet()
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
            record = {"address": address, "used": False}
            self.address_records.insert(0, record)
        record["label"] = label
        self._persist_current_wallet()
        self.verify_address_input.clear()
        self.verified_address_label.clear()
        self.stack.setCurrentIndex(6)

    def _invalidate_psbt_review(self):
        self.reviewed_psbt = None
        self.reviewed_id = None
        self.sign_button.setEnabled(False)
        self.review_panel.hide()
        _clear_layout(self.review_layout)
        self.authorize_panel.hide()
        self.review_details_toggle.setChecked(False)
        self.review_details_toggle.hide()
        self.replace_psbt_button.hide()
        self.signed_panel.hide()
        self.psbt_import_panel.show()
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
            self.verify_result.show()
            self.verify_done.setEnabled(False)
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
            self.verify_done.setEnabled(True)
        else:
            self.verify_result.setText("This address does not belong to the current wallet.")
            self.verify_result.setProperty("verified", False)
            self.verified_address_label.setEnabled(False)
            self.verify_done.setEnabled(False)
        self.verify_result.show()
        self.verify_result.style().unpolish(self.verify_result)
        self.verify_result.style().polish(self.verify_result)
        self.verify_result.updateGeometry()

    def _clear_address_result(self):
        self.verify_result.clear()
        self.verify_result.hide()
        self.verify_done.setEnabled(False)
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
        self._render_transaction_review(review)
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
            self._replace_transaction()
            QMessageBox.warning(self, "Signing failed", str(exc))
            return
        self.signer_password.clear()
        self.sign_button.setEnabled(False)
        self.authorize_panel.hide()
        self.signed_panel.show()
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
        self.export_return_index = self.stack.currentIndex()
        payload = self.descriptors.toPlainText()
        try:
            pixmap = self._qr_pixmap(payload, size=480)
        except (ValueError, DataOverflowError):
            pixmap = None
        if not hasattr(self, "export_qr"):
            layout = self._card(scroll=True, surface=False)
            self._add_back_heading(layout, "Export watch-only wallet", "Scan this public wallet with your online node.", 12)
            content = QHBoxLayout()
            content.setSpacing(24)
            self.export_qr = QLabel()
            self.export_qr.setObjectName("QR")
            self.export_qr.setFixedSize(480, 480)
            self.export_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.export_qr.setWordWrap(True)
            content.addWidget(self.export_qr, 0, Qt.AlignmentFlag.AlignTop)
            data_panel = _panel(content, "Public wallet backup", "One receive/change descriptor for Sparrow and other descriptor wallets.")
            self.export_text = QPlainTextEdit()
            self.export_text.setReadOnly(True)
            self.export_text.setFont(fixed_font(10))
            self.export_text.setMinimumHeight(180)
            self.export_text.setToolTip("Public wallet name and receive/change descriptors. Keep this backup for multisig recovery.")
            self.export_text.installEventFilter(self)
            data_panel.addWidget(self.export_text, 1)
            note = _label("Contains no recovery phrase or private keys.", True)
            data_panel.addWidget(note)
            layout.addLayout(content)
            layout.addStretch()
            footer = QHBoxLayout()
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
        path, _ = QFileDialog.getSaveFileName(self, "Save public wallet backup", "wallet-descriptor.txt", "Text files (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.export_text.toPlainText() + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Could not save wallet backup", str(exc))

    def _confirm_close(self):
        if self.wallet_ready:
            return self._persist_current_wallet()
        if self.multisig_prepared or self.phrase:
            return QMessageBox.question(self, "Leave unfinished setup?",
                "This unfinished setup has not been saved. Keep your recovery phrase before leaving.",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Close,
                QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Close
        return True

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

    def _persist_current_wallet(self):
        if not self.wallet_ready or self.core is None:
            return True
        try:
            self.core.save_wallet({"name": self.wallet_display_name, "wallet_type": self.wallet_type_summary,
                "address_type": self.core.address_type, "result": self.wallet_result,
                "address_records": self.address_records, "hidden_addresses": self.hidden_addresses})
        except (ColdSetupError, CoreError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Wallet not saved", str(exc))
            return False
        return True

    def _refresh_saved_wallets(self):
        self.saved_wallets.clear()
        if self.core is not None:
            try:
                for wallet_id, name in self.core.store.list_wallets():
                    metadata = self.core.store.read_metadata(wallet_id)
                    encrypted = metadata.get("encrypted", metadata["result"].get("encrypted", True))
                    status = "Encrypted" if encrypted else "Unencrypted"
                    self.saved_wallets.addItem(f"{name} · {status}", wallet_id)
            except (OSError, ColdSetupError) as exc:
                QMessageBox.warning(self, "Wallet storage unavailable", str(exc))
        available = self.saved_wallets.count() > 0
        self.open_saved_button.setEnabled(available)
        self.saved_wallets.setEnabled(available)
        if not available:
            self.saved_wallets.addItem("No saved wallets", None)

    def _open_saved_wallet(self):
        wallet_id = self.saved_wallets.currentData()
        if not wallet_id or self.core is None:
            return
        try:
            metadata = self.core.open_saved_wallet(wallet_id)
            self.wallet_name_input.setText(metadata["name"])
            self.wallet_mode = "multisig" if metadata["result"].get("signers") else "single"
            self.address_records = metadata.get("address_records", [])
            self.hidden_addresses = metadata.get("hidden_addresses", [])
            self._show_complete(metadata["result"], metadata["wallet_type"])
        except (ColdSetupError, CoreError, KeyError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not open wallet", str(exc))

    def _remove_address(self):
        if not self.active_address:
            return
        answer = QMessageBox.question(self, "Remove address from list?",
            "The address will remain part of your wallet and can still receive bitcoin.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            self.hidden_addresses.append(self.active_address)
            self.address_records = [r for r in self.address_records if r["address"] != self.active_address]
            self._persist_current_wallet()
            self._open_addresses()

    def _set_advanced_bip39(self, enabled):
        QSettings("CoreCompanion", "CoreCompanion").setValue("bip39_enabled", enabled)
        if hasattr(self, "bip39_panel"):
            self.bip39_panel.setVisible(enabled)
            if not enabled:
                self.use_bip39_passphrase.setChecked(False)

    def _go_back(self):
        page = self.stack.currentIndex()
        if page == 15:
            self._finish()
        elif page == 4:
            self._back_from_confirmation()
        else:
            targets = {0: 16, 1: 0, 2: 0, 3: 1, 5: 17, 7: 6, 8: 9, 9: 6,
                       10: 6, 11: 10, 12: 6, 13: 12, 14: getattr(self, "settings_return_index", 12 if self.wallet_ready else 15),
                       16: 15, 17: 2 if self.phrase_source == "recover" else 4}
            self.stack.setCurrentIndex(targets.get(page, getattr(self, "export_return_index", 12)))

    def _page_changed(self, page):
        self.global_back.setVisible(page != 6)
        if page == 9 and self.wallet_ready:
            QTimer.singleShot(0, self._start_qr_scanner)
        elif self.scanner is not None:
            self._stop_scanner()

    def _open_settings(self):
        self.settings_return_index = self.stack.currentIndex()
        self.stack.setCurrentIndex(14)
