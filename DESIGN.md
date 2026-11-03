# Desktop design branch

`design/desktop-polish` is an interface exploration for review alongside `main`.
The application uses native PySide6 Qt Widgets and the existing dependency lock.

## Direction

- A precise desktop workspace with clear text and consistent line icons.
- Blue identifies cold storage; red identifies the online watch-only node.
- Both light and dark themes have explicit text, border, focus and error colors.
- Navy identity panels and restrained native gradients give the application a
  consistent visual identity. Fingerprint and scanner artwork use Qt painting,
  with no external assets, new dependencies, animation, or network requests.
- Wallet identity and signer fingerprint are prominent. The visual fingerprint
  is a recognition aid; it is not a substitute for checking the wallet policy.
- Setup has a compact progress strip. Optional explanations live in tooltips
  and entropy audit data stays collapsed.
- Setup, recovery, protection, policy, export, and import views share the same
  field labels, form panels, navigation, help controls, and focus treatment.
  Native selectors retain their behavior and have explicit dropdown indicators.
- Empty lists explain the next step. Verification results have distinct match
  and mismatch states; address labels become available only after a match.
- Recovery words appear in numbered tiles. Confirmation and session cleanup
  continue to clear the visible secret fields.
- Transaction review separates every output, amount and classification supplied
  by Core. Addresses and nonstandard scripts are shown in full. Large or complex
  reviews use the complete text view to bound the number of created widgets.
- Editing or replacing a PSBT revokes its review. Signing continues to pass
  Core's canonical PSBT and the exact reviewed transaction identifier.
- Enter activates the focused button. Enter in the wallet-name field continues
  setup, while Enter in a signing-password field does not initiate signing.

## Review map

`companion/theme.py` contains the shared palettes and styles;
`companion/widgets.py` contains icons, selectable choices and action controls.
`companion/ui.py` contains the welcome and online layouts;
`companion/cold_ui.py` contains the signer screens and review presentation.

The branch makes no changes to the RPC client, wallet service, entropy recipe,
Core download verification, offline Core implementation, host isolation,
dependency lock, or installer.

The final native Qt review rendered 140 screen states in light/dark modes at
1280×850 and 980×680 on Windows and in the existing Linux WSL environment.
Import dialogs were also checked in both themes. Eleven fixture interaction
checks cover complete detailed reviews, PSBT review invalidation, canonical
signing arguments, recovery-field clearing, help, and keyboard activation.
The review reported no missing-help or horizontal-overflow warnings. These
checks do not constitute a security audit or replace Debian host-isolation
acceptance.
