# Upstream sync: conflict policy and recovery

Date: 2026-09-22
Status: Approved, not yet implemented

## Problem

`.github/workflows/sync-upstream.yml` mirrors `boneIO-eu/app_black:dev-debian13`
into this fork. It has failed on every scheduled run since 2026-09-17 — six
consecutive days — and would have kept failing indefinitely.

The workflow applies the upstream range as one patch:

```bash
git diff --binary --full-index "$BASE_SHA" "$BATCH_END" > "$patch_file"
if [[ -s "$patch_file" ]] && ! git apply --3way --index "$patch_file"; then
  echo "The selected range ... conflicts with ${TARGET_BRANCH}." >&2
  exit 1
fi
```

Any conflict is a hard `exit 1`. No branch is pushed, no PR is opened, no issue
is filed. The only signal is a red X on a scheduled run.

Replaying the exact failing range (`938a1d6b..6cf03bfb`) locally gives the full
picture, which the truncated CI log hides:

- 199 files apply cleanly
- 18 files apply with conflicts
- 4 files fail outright (`does not exist in index`, `patch does not apply`)

Three distinct defects sit behind that failure.

### Defect 1: conflicts fail silently and permanently

A conflict produces no reviewable artifact. Nothing surfaces the problem to a
human, and the next scheduled run repeats the identical failure.

### Defect 2: the batch is two months wide

`.github/upstream-sync-state.json` has never existed on `main` — no sync PR has
ever merged. So `base_sha` falls back to `git merge-base HEAD "$source_sha"`,
the fork point, and the batch is 300+ commits, 320 files, a 4.9 MB patch.

Every prior "success" was the no-op path: `Target is already up to date`. The
workflow has never once produced a sync PR.

### Defect 3: some files conflict on every sync by construction

The 22 problem files sort into six classes. Only the last needs human judgement.

| Class | Files | Why it conflicts |
| --- | --- | --- |
| Regenerable locks | `uv.lock`, `frontend/pnpm-lock.yaml` | Both sides ran dependency updates independently. Textually unmergeable, but derivable from their manifests |
| Upstream deleted | `frontend/package-lock.json` | Upstream went pnpm-only and removed it; the fork still carries 343 KB of it |
| Fork deleted | `.github/workflows/publish-to-pypi.yaml` | Upstream edits a file this fork removed |
| Fork owned | `boneio/version.py`, `CHANGELOG.md`, `.gitignore`, `.github/workflows/test.yml` | Deliberate, permanent divergence |
| Semantic manifests | `pyproject.toml`, `frontend/package.json` | See below |
| Genuine code overlap | `boneio/core/messaging/mqtt.py`, `boneio/webui/app.py`, `boneio/webui/routes/__init__.py`, `UISettings.tsx`, `SystemState.tsx`, `SettingsSidebar.tsx`, `sectionDefinitions.ts`, `locales/en/common.json`, `locales/pl/common.json`, `vite.config.ts`, `ConfigEditorUI.tsx`, `yamlConverter.ts` | Upstream's settings-UI restructuring against this fork's Lox/MQTT bridge, MQTT device groups and alternative update source |

The manifest class deserves detail, because git is using the wrong tool on it.

Fork-side `pyproject.toml` divergence is 42 lines: 4 are real fork identity
(name, description, authors, repository URL); the rest are dependency pins that
upstream bumps independently. Several bumps are **byte-identical on both sides**
(`aiohttp` 3.14.1 to 3.14.3, `fastapi` 0.118.0 to 0.141.1) and would merge
cleanly line-by-line. But git merges by hunk, so contiguous pin lines conflict
en bloc. Only two pins genuinely differ — `python-multipart` (0.0.32 fork vs
0.0.31 upstream) and `requests` (2.34.2 vs 2.33.0), fork ahead in both — yet the
whole dependency block conflicts.

Meanwhile upstream made structural dependency changes this fork wants: dropped
`python-jose[cryptography]` for `PyJWT==2.14.0`, swapped `httpx` for `httpx2`,
added `starlette`, `anyio`, `cryptography` and `astral`, and bumped
`aioesphomeapi` from 29 to 45. A blunt "fork always wins" on `pyproject.toml`
would silently discard all of it, including an apparently security-motivated JWT
library migration.

Upstream also renamed its own repository (`app_bbb` to `app_black`), so even the
`Repository` URL is a live conflict.

## Context and constraints

- This fork is a **close tracker**: the intent is to absorb all upstream work
  continuously and keep divergence minimal.
- Genuine fork divergence is substantial and must be protected: 80 files,
  +8520/-4037 lines — Lox/MQTT bridge, MQTT device groups, alternative update
  source, bilingual release notes, `install.sh`, rebranding.
- **Fork-side Dependabot stays enabled** for all four ecosystems. This was
  considered and explicitly decided. The consequence is that dependency
  collisions must be absorbed mechanically rather than prevented, which makes
  the regeneration and manifest-resolver layers load-bearing rather than
  optional.
- The state-file model is kept. It was chosen so that squash, rebase and
  merge-commit PRs all advance to the same next batch; switching to a real
  `git merge` would trade that for a branch-protection rule.
- CI facts that bear on the design: `test.yml` pip-installs a hardcoded
  dependency list (including `python-jose`, which upstream just dropped), so CI
  pins drift independently of `pyproject.toml`. `uv` appears nowhere in CI.
  The frontend job runs `pnpm install --no-frozen-lockfile`, so
  `pnpm-lock.yaml` is advisory in CI today.

## Design

### Pipeline

The single apply step becomes a staged pipeline. Steps 1, 2 and 8 are today's
behaviour; 3 through 7 are new.

1. Select batch, now capped (see Batch bounding)
2. `git diff --binary --full-index BASE..END > patch`
3. **Filter** the patch through the policy file, dropping hunks for fork-owned,
   fork-deleted, upstream-deleted, regenerable and semantically-merged paths
4. `git apply --3way --index` the remainder
5. **Resolve manifests** semantically
6. **Regenerate locks**
7. **Triage**: scan for surviving conflict markers
8. State file advances on merge (unchanged)

Implementation lives in `scripts/upstream_sync/` as Python. The repository
already unit-tests scripts under `tests/unit/scripts/`, so there is both
precedent and a test home.

### Policy file

`.github/upstream-sync-policy.yml` declares six classes. Applied to the current
backlog it handles 10 of the 22 problem files.

```yaml
fork_owned:          # upstream's changes dropped, and reported in the PR body
  - boneio/version.py          # release-please owns this
  - CHANGELOG.md
  - CHANGELOG.pl.md
  - release-please-config.json
  - .release-please-manifest.json
  - .github/workflows/**
  - .github/dependabot.yml
  - install.sh
  - README.md

fork_deleted:        # upstream edits files we removed; dropped silently
  []                 # currently empty: fork_owned's .github/workflows/**
                     # already covers publish-to-pypi.yaml. Kept as a class
                     # because non-workflow deletions will need it.

upstream_deleted:    # upstream removed it; fork follows
  - frontend/package-lock.json

union:               # keep both sides' lines, dedupe
  - .gitignore

regenerate:          # never merged textually; rebuilt from the manifest
  - path: uv.lock
    command: uv lock
  - path: frontend/pnpm-lock.yaml
    command: pnpm install --lockfile-only --dir frontend

manifests:           # merged semantically
  - path: pyproject.toml
    identity_keys: [project.name, project.description, project.authors,
                    project.urls.Repository, project.urls.Changelog]
  - path: frontend/package.json
    identity_keys: [name, description, repository]
```

Changes dropped under `fork_owned` are **listed in the PR body**. Without that
report, upstream's evolution of those files vanishes silently and permanently,
and nobody ever ports anything across.

`fork_deleted` and `upstream_deleted` use the same drop mechanism but are
reported differently: the former is expected and silent, the latter means the
fork should follow upstream in removing the file.

### Upstream additions are inherited by default

A file upstream *adds* after the fork point carries no conflict — the patch
creates it and the fork silently gains it. `.github/workflows/sbom.yml` is a
live example: upstream added it after the fork point, so it applies cleanly and
would introduce a new upstream CI workflow into this fork without anyone
deciding to accept it.

For a close tracker that default is usually right, and deliberately so. It is
wrong for `.github/workflows/**`, where inheriting upstream CI means running
jobs against this fork's different release machinery and secrets. The
`fork_owned` glob `.github/workflows/**` closes that hole for both additions and
modifications, which is why the `fork_deleted` list needs no workflow entries.

### Manifest resolver

Per dependency, in order:

- **Start from upstream's file**, so structural changes come through — the
  `python-jose` to `PyJWT` swap, `httpx` to `httpx2`, the new `starlette`,
  `anyio`, `cryptography` and `astral` entries
- **Re-apply fork identity keys** on top, from `identity_keys` in the policy
- **Only one side moved a pin** — take that side
- **Both sides moved a pin up** — take the higher version. PEP 440 comparison
  for Python, semver for npm
- **Upstream moved a pin down relative to base** — flag for human review, never
  auto-resolve. A downgrade is usually a deliberate pin-back after a regression,
  and "higher wins" would silently undo it

Every decision is emitted as a table in the PR body, so the merge is auditable
rather than magic.

### Conflict handling

The core fix: a conflict must never again be an invisible `exit 1`.

- **Conflicts survive triage** — commit the tree with markers, push the branch,
  open a **draft** PR labeled `upstream-sync-conflict`. The body groups
  conflicted files by class and includes the resolver's decision table.
- The existing "Stop if another sync PR is open" guard then pauses the schedule
  until a human deals with it. That machinery already works today; it simply
  never gets reached, because the workflow dies before pushing anything.
- A human resolves on the branch, pushes, and marks the PR ready.
- **Genuine errors** — regeneration fails, upstream history rewritten, policy
  file malformed — open or update a tracking issue titled
  `upstream sync blocked`, so the failure has a mouth.

A branch containing `<<<<<<<` markers will fail `test.yml` red. This is accepted
deliberately: it is honest signal on a draft PR explicitly labeled as
conflicted, and is preferred over weakening `test.yml` with a skip-guard.

### Batch bounding

Cap each batch at N upstream first-parent commits. Default `N=25`, overridable
via the repository variable `UPSTREAM_SYNC_BATCH_SIZE`. Cut only at first-parent
boundaries, so a merge made upstream remains atomic — preserving the property
the current workflow documents. Never split below a single first-parent commit.

Once the fork is caught up, daily batches are 0 to 3 commits and this never
binds. It matters only for digging out of the current backlog and after any
future outage.

### Testing

- Unit tests for the three scripts: patch filter, manifest resolver, version
  comparator. The comparator's downgrade-flag case is explicitly covered.
- **Replay harness**: run the whole pipeline against the real
  `938a1d6b..6cf03bfb` backlog as a fixture and assert the surviving conflict
  set is exactly the 12 genuine files listed in Defect 3. This pins the policy's
  behaviour against real data and catches regressions when the policy file is
  edited later.

## Scope boundary

The 300-commit catch-up is a **separate, human-driven PR**. No part of this
design automates it. The 12 genuine code conflicts are real collisions between
upstream's settings-UI restructuring and this fork's Lox/MQTT bridge and
update-source work, and they need judgement.

Sequencing: **ship the workflow first**, let it open the conflict PR for the
backlog, then resolve that PR by hand. The new machinery then does the
mechanical two-thirds of the catch-up rather than a human doing all of it.

## Rejected alternatives

**Switch to a real `git merge`.** The fork already shares ancestry with
upstream, so a sync branch could simply `git merge source/dev-debian13`. Git
would compute the merge base natively, `git rerere` would remember every
resolution, and `.gitattributes` merge drivers would apply automatically —
including to local merges. Rejected because it only works if sync PRs are merged
with a merge commit; a squash or rebase merge silently discards the ancestry and
every conflict must be re-resolved forever. The state-file model was chosen
precisely to survive any merge strategy, and betting the pipeline on nobody
clicking "Squash and merge" is a fragile foundation.

Note that `.gitattributes` merge drivers do not apply to `git apply --3way` at
all — only to real merges. This is why the policy must be its own filter layer
rather than something git enforces natively.

**Minimal fix: only make failures visible.** Replace `exit 1` with a draft PR
and a tracking issue, and stop there. Cheap, and it stops the silent rot, but it
leaves the full recurring conflict load on a human every single sync.

**Retire fork-side Dependabot for the shared ecosystems.** Dropping the `pip`,
`npm` and `docker-compose` entries from `.github/dependabot.yml` while leaving
Dependabot *security* updates enabled at the repository level would have removed
6 of the 18 conflicting files permanently and reduced `pyproject.toml` to a
clean 4-line merge. Considered and explicitly rejected: fork-side Dependabot is
kept for all four ecosystems, in exchange for the mechanical absorption layers
described above.
