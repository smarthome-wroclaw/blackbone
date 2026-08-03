# README: fork disclosure, installation, and contributing — design

Date: 2026-08-04
Branch: `readme-fork-install`

## Context

This repository is `smarthome-wroclaw/blackbone` (remote `private`; will become public), a fork
of the upstream boneIO application (`boneIO-eu/app_bbb`, `https://boneio.eu`). The current
`README.md` is minimal (607 bytes): just an example usage snippet and a fresh-install block
(apt packages + venv + `pip install boneio`). It does not state that this is a fork, does not
document how to move an existing client controller onto the fork, and has no contributing
section.

A separate, already-written installer script exists on branch `pr/blackbone-installer`
(not yet merged to `main`): `install.sh` at the repo root. It is interactive, detects the
existing venv (checked in order: `/home/boneio/boneio/venv`, `~/boneio/venv`, `~/venv`,
`/opt/boneio/venv`), optionally backs up the current config and installed app, runs
`pip install --upgrade --force-reinstall blackbone`, and restarts the `boneio` systemd
service. Its own header comment documents the intended usage:

```
curl -fsSL https://raw.githubusercontent.com/smarthome-wroclaw/blackbone/main/install.sh | bash
```

This README change references that command directly, on the assumption that
`pr/blackbone-installer` lands in `main` independently (confirmed with the user — no need to
block this PR on that merge).

Two logo files were provided for the README header:
- `/Users/artur/Downloads/blackbone-black.svg` — for light backgrounds
- `/Users/artur/Downloads/blackbone-white.svg` — for dark backgrounds

## Goals

1. State clearly, near the top of the README, that this project is a fork of boneIO, built
   and maintained by smarthome-wroclaw, not affiliated with or endorsed by the original
   boneIO authors, adding features developed for and validated in real client installations.
2. Add a section documenting how to move an existing, already-deployed controller (currently
   running the original boneIO app) onto this fork via SSH + the `install.sh` one-liner.
3. Add a short Contributing section pointing to GitHub Issues/PRs.
4. Add a logo to the top of the README that renders correctly in both GitHub's light and dark
   themes.
5. Keep the existing fresh-install instructions (apt/venv/pip) — they remain accurate for a
   from-scratch install of the (still PyPI-named) `boneio` package and are out of scope here.
6. The whole README is bilingual: **all EN content first, all PL content below it** — one
   full parallel translation block, not interleaved per-section.
7. Record the bilingual-documentation convention in `.agents/AGENTS.md`, extending it beyond
   PR descriptions (its only prior scope) to user-facing docs like the README.

## Non-goals

- Renaming the `boneio` PyPI package / `pyproject.toml` project name to `blackbone` — that is
  the responsibility of the separate installer/packaging work, not this README change.
- Changing the existing fresh-install block's package name or steps.
- Merging `pr/blackbone-installer` into `main` as part of this change.
- Per-section EN/PL interleaving.

## Design

### 1. Logo assets

Copy both provided SVGs into the repo at:
- `docs/assets/blackbone-black.svg`
- `docs/assets/blackbone-white.svg`

At the very top of `README.md`, use a `<picture>` element with `prefers-color-scheme` media
queries (GitHub honors this in rendered READMEs) so the correct logo shows per viewer theme:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/blackbone-white.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/blackbone-black.svg">
  <img alt="BlackBone" src="docs/assets/blackbone-black.svg" width="320">
</picture>
```

### 2. README structure (top to bottom)

1. Logo (`<picture>` block above)
2. **EN block:**
   - Fork disclaimer / intro paragraph
   - Existing "Example usage" + fresh-install content, unchanged
   - New "Upgrading an existing controller to BlackBone" section
   - New "Contributing" section
3. **PL block:** full translation of everything in the EN block, same order, below a clear
   separator (e.g. `---` and a `## Polski` heading).

### 3. Fork disclaimer copy (EN, PL to mirror)

Communicates: this is a fork of boneIO (link to `https://boneio.eu` and
`https://github.com/boneIO-eu/app_bbb`), maintained by smarthome-wroclaw, adds features built
for and proven in real client installations, not affiliated with or endorsed by the original
authors, same GPLv3 license as upstream.

### 4. Upgrade section content

- Brief one-line explanation: for controllers already running the original boneIO app.
- Step: SSH into the controller.
- Step: run the installer:
  ```
  curl -fsSL https://raw.githubusercontent.com/smarthome-wroclaw/blackbone/main/install.sh | bash
  ```
- One or two lines describing what the script does (detects the existing venv, offers to back
  up config and the current app, installs the fork, restarts the `boneio` service) so users
  aren't surprised by its interactive prompts.

### 5. Contributing section content

Short blurb (no formal process/checklist per user's choice): welcomes issues and pull requests,
links to the GitHub repo's Issues/PRs.

### 6. `.agents/AGENTS.md` update

Add a line noting that bilingual (EN primary / PL secondary) output applies to user-facing
documentation such as the README, not only PR descriptions — the prior undocumented convention
this generalizes.

## Testing / validation

Documentation-only change. Validation is manual review:
- Render `README.md` on GitHub (or a local Markdown/HTML preview) to confirm the `<picture>`
  logo swap behaves correctly in both themes.
- Proofread both language blocks for consistency with each other.
- Confirm the curl command matches `install.sh`'s own documented usage comment exactly.
