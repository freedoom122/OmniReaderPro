# Veyrion Workspace — Security

This document describes the security model honestly: what is protected, how,
and — just as importantly — what is *not* guaranteed. We do not claim
"military-grade" anything. Claims here are limited to what the implementation
actually does.

## Threat model

Assumed adversary: documents you open are potentially malicious files
(PDF/EPUB/DOCX/HTML/SVG/archives can embed scripts, link to network
resources, exploit parsers, or be crafted to crash or exhaust resources).
Also assumed: the machine is shared or observed, so local data deserves
protection; network is untrusted.

Out of scope: protecting against an attacker who already has full control of
the OS account (no user-space application can); keyloggers; hardware-level
attacks; and protecting the *original* file from a determined attacker with
forensic hardware.

## Trust boundaries

| Boundary            | Trusted? | Notes                                                  |
| ------------------- | -------- | ------------------------------------------------------ |
| Application code    | Trusted  | Ships signed only by build integrity; runs your machine |
| Document files      | Untrusted| Parsed defensively; never executed                     |
| Plugins             | Untrusted| Permission-declared, user-approved, facade-gated       |
| Network             | Untrusted| Off by default; gated by Offline Mode                  |
| Local user data     | Trusted  | Protected at rest in the vault                         |

## Untrusted document handling

- **Format detection by extension + defensive parsing.** Unknown or
  malformed files produce a friendly error, never a crash.
- **Path safety:** null bytes, empty names, Windows device names (`CON`,
  `NUL`), drive-absolute and traversal paths are rejected before use
  (`utils/pathutils.py`).
- **Archives (CBZ/CBR/ZIP):** extraction validates every member before
  writing, blocks traversal (`../`, `..\`, absolute paths), caps total
  decompressed size, per-entry compression ratio (zip-bomb guard), and file
  count; output goes to a controlled app temp directory.
- **No code execution from documents.** PDF JavaScript is never executed;
  HTML is never loaded with scripts enabled; SVG is treated as an image
  where rendered.
- **Resource limits:** rendering is lazily cached with a bounded budget;
  huge files fail with a clear message instead of exhausting memory.

## Plugin security

Plugins are Python code from disk — treat them like any executable.

- Every plugin declares permissions in `plugin.json`:
  `filesystem.read`, `filesystem.write`, `network`, `clipboard`,
  `document.read`, `document.write`.
- The host validates id format, entry-point containment within the plugin
  folder, and rejects undeclared permissions before import.
- Nothing is imported until the user approves the plugin (approval is
  remembered in settings and revocable).
- Plugins receive a `PluginFacade`, not application internals; every facade
  method re-checks the granted permission. Denials raise `PermissionError`.
- Network permission additionally requires `"trusted": true` in the
  manifest as a manual-review signal.
- Invalid or crashing plugins are disabled with an explanation, never
  allowed to take the app down.

## Network behavior

- **Default: no network use at all.** No telemetry, analytics, tracking,
  advertising, or silent uploads. No update pings (update checks default
  off).
- Network-capable features (Wikipedia lookup, web translation fallback,
  update check) are explicit, user-initiated, and visible.
- **Offline Mode** (default on) blocks all network features globally.
- External links in documents are never auto-opened: the destination is
  shown and the user chooses open/copy; a per-site remember option exists;
  arbitrary executables are never launched.

## Encryption (the vault)

- Algorithm: **AES-256-GCM** (authenticated encryption) via the
  `cryptography` package.
- Key derivation: **PBKDF2-HMAC-SHA256, 600,000 iterations**, random
  16-byte salt per vault, random 12-byte nonce per item. Argon2id is
  preferred but has no dependable pinned Windows wheel for Python 3.13 at
  the time of writing (see DECISIONS.md).
- The derived key exists only in memory while unlocked and is zeroized on
  lock. The password is never stored. Auto-lock (manual or after a
  configurable inactivity timeout) clears the key material.
- **Limits:** A weak password is still a weak password — no KDF makes
  `password123` safe. PBKDF2-SHA256 is GPU-parallelizable; choose a long
  passphrase. The vault protects data at rest; it does not protect against a
  compromised session.

## Redaction

True redaction is implemented: `apply_redactions` removes the covered text
and (where applicable) pixels, and the saved file is sanitized. The app
offers **Verify Redaction**, which reopens the produced file, searches for
the affected phrases, inspects page content, and reports.

**Honest limits:**
- Content buried inside malformed or incremental-update structures may not
  be fully removable; verification reports what it finds.
- No tool can guarantee against future forensic analysis of the *original*
  file on disk — redaction creates a sanitized copy; delete the original
  securely (and note that NTFS journaling may still permit recovery).
- "Verified" means: the phrases were not found and page objects were
  inspected with the tools described. It is not an absolute proof.

## Secure deletion

`secure_delete` overwrites the file with random data (3 passes) before
unlinking. On NTFS (and most journaling filesystems) this reduces but does
not guarantee unrecoverability. For high-sensitivity data, use OS-level
full-disk encryption and a shredding utility outside this application.

## Database

SQLite runs in WAL mode with transactions and versioned migrations. The
database is protected by OS file permissions; the vault is the layer that
provides encryption. We do not store passwords or vault keys in the
database. A damaged database triggers migration/backup recovery, never
silent data destruction.

## Logging & diagnostics

Logs contain timestamps, module names, and error descriptions — never
document contents, passwords, notes, or keys. The diagnostic report export
sanitizes local paths. Logs live in the app-data `logs/` directory.

## Reporting vulnerabilities

Please report security issues privately to the maintainers with a
reproducer. Include: affected version, OS, and the minimal file/sequence
that triggers the issue. We treat reports with priority and will acknowledge
them.

## Known limitations (summary)

1. Redaction/sanitization completeness is bounded by the PDF format (see
   above).
2. Secure deletion is best-effort on journaled filesystems.
3. The vault KDF is PBKDF2, not Argon2id (see DECISIONS.md).
4. No cryptographic *creation* of signatures in this build — signatures are
   inspected and reported; visual signatures are labeled as non-cryptographic.
5. Plugins are powerful by design once approved — approve only plugins you
   trust.
6. Network features are only as private as their endpoints; Offline Mode is
   the only absolute guarantee of no traffic.