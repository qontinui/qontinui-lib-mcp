# Contributing

Thanks for your interest in contributing to qontinui. This document explains how to submit changes and what you're agreeing to when you do.

## License: AGPL-3.0-or-later

This project is licensed under the **GNU Affero General Public License v3 or later** (`AGPL-3.0-or-later`). The full text is in [`LICENSE`](LICENSE).

What this means for you as a contributor:

- Anyone can use, modify, and redistribute the code under the same AGPL terms.
- If you (or anyone else) runs a modified version of qontinui as a network service, the AGPL requires you to publish your modifications under AGPL too — this is the "network copyleft" provision and the reason this project chose AGPL.
- For typical self-hosting, internal use, forking, or contributing back, AGPL is no different from GPL in practice.

If your employer has policies about contributing to AGPL projects, please confirm with them before you submit a PR.

## Contributor License Agreement (CLA)

All non-trivial contributions require signing the qontinui CLA before they can be merged. The CLA grants Joshua Spinak (the project author) the right to relicense your contribution under any future license — this is the standard open-core pattern (Apache, Google, MongoDB, GitLab all use a similar CLA) and exists so the project can adapt its license posture in the future without re-litigating contributor consent.

The CLA does **not** transfer copyright. You retain copyright in your contributions; you grant a relicensing right.

**How to sign:** the project uses [cla-assistant.io](https://cla-assistant.io/) — when you open a pull request, the CLA bot will comment with a one-click link. Sign once and the bot remembers you across all qontinui repositories. The CLA text is also kept in [`CLA.md`](CLA.md) for reference.

Trivial changes (typo fixes, single-line documentation tweaks) do not require a CLA, at the maintainer's discretion.

## Code style

This repository follows the conventions documented in `CLAUDE.md` (project root). Highlights:

- Edit existing files in preference to creating new ones; keep changes scoped to the task.
- No comments unless the *why* is non-obvious. Don't narrate what well-named code already says.
- No backwards-compatibility shims unless explicitly requested.
- For Python: Black + ruff. For TypeScript/JavaScript: project's Prettier + ESLint config. For Rust: `cargo fmt` + `cargo clippy`.
- Run the test suite before opening a PR. CI will reject unformatted or lint-failing code.

## Submitting a change

1. Fork the repository and create a feature branch.
2. Make your change. Add tests where appropriate.
3. Run the local checks (lint, format, tests) — the per-repo `README` documents the exact commands.
4. Open a pull request against `main`. Describe the *why* in the PR body, not the *what* — the diff already shows the *what*.
5. Sign the CLA if the bot prompts you.
6. A maintainer will review. Expect feedback; we keep the bar high because every change becomes part of the shipped product.

## Reporting bugs / requesting features

Open a GitHub issue. For security vulnerabilities, please email the maintainers directly rather than filing a public issue.

## Code of conduct

Be kind. Be specific. No harassment. Discussions stay on the technical merits.
