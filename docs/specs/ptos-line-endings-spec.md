# PTOS Line-Ending Normalization Spec

Status: accepted
Location: `docs/specs/ptos-line-endings-spec.md`
Repo: `godwinburby/ptos` (audited at `2f9cb5a`, 2026-10-29)

## 1. Problem

Whole-file CRLF rewrites are landing in ordinary commits. A 28-line change shows as ~19,000 changed lines. This breaks `git blame`, makes review of AI-written diffs unreliable, and will complicate the planned personal-data history purge.

No `.gitattributes` exists and `core.autocrlf` is unset in the audited clone, so nothing in the repo stops it.

## 2. Audit findings

Scanned the last 60 of 769 commits (history starts 2026-03-09). Commits where raw diff size exceeds the real (`--ignore-space-at-eol`) diff by more than 200 lines:

| Commit | Raw lines | Real lines | Subject |
|---|---|---|---|
| `2f9cb5a` | 19,018 | 28 | Fix manage panel name validation and key prefix handling |
| `11d0fa6` | 1,909 | 49 | Add page manage panel render tests |
| `69f0504` | 13,982 | 2,230 | Wave 2: migrate browse + queries pages to controllers |
| `2b56814` | 920 | 18 | Fix todo page mobile overflow and remove home preview toggle |
| `be07621` | 10,730 | 2,158 | Migrate todo page to widget shell (Wave 3 T1-T4) |

All five are from Oct 28-29, so the problem is recent and accelerating, not historical.

Current state of tracked files at HEAD (`git ls-files --eol`):

| Index state | Files |
|---|---|
| `i/lf` | 249 |
| `i/crlf` | 17 |
| `i/mixed` | 3 |
| `i/none` (empty) | 16 |
| `i/-text` (binary) | 10 |

CRLF files include the core ones: `ptos_service.py`, `ptos_web.py`, `ptos_widgets.py`, `tests/test_scoped_writes.py`, `CHANGELOG.md`, several `web_static/js/*` and `web_static/css/*`, `web_templates/home.html`, `web_templates/page_shell.html`.

Mixed (both endings inside one file): `tests/test_links.py`, `web_static/js/widget_host.js`, `web_static/js/widgets.js`.

Cause (confirmed by Godwin): Kilo Code, running on the Windows work machine, writes files with CRLF. Most of the repo is still LF, so files are being converted one by one as the agent touches them. Tool in use: Kilo Code CLI. The exact mechanism is unverified: the CLI may write with Windows line endings itself, or preserve them in files that were already CRLF. Either way, `.gitattributes` with `eol=lf` normalizes on commit regardless of what the agent writes, so it is the primary fix.

## 3. Goal and non-goals

Goal: LF in the repository for all text files, except Windows scripts that need CRLF. Diffs show only real changes.

Non-goals: changing file contents, reformatting code, rewriting history (see section 6).

## 4. Changes

### 4.1 `.gitattributes` (new, repo root)

```
* text=auto eol=lf

# Windows scripts must stay CRLF
*.bat text eol=crlf
*.cmd text eol=crlf
*.ps1 text eol=crlf

# Binary
*.ico binary
*.png binary
*.jpg binary
*.webp binary
*.woff2 binary
```

Check the 10 `i/-text` files with `git ls-files --eol | grep 'i/-text'` and add any extension not covered above.

### 4.2 `.editorconfig` (new, repo root)

```
root = true

[*]
end_of_line = lf
insert_final_newline = true
charset = utf-8

[*.{bat,cmd,ps1}]
end_of_line = crlf
```

### 4.2b VS Code workspace setting (new, for Kilo Code)

Commit `.vscode/settings.json` so it applies on every machine that opens the repo:

```json
{
  "files.eol": "\n"
}
```

This setting only affects the Kilo Code VS Code extension. Godwin uses the Kilo Code CLI, which writes files itself and does not read VS Code settings, so for the CLI the real protection is `.gitattributes` (4.1, which converts CRLF to LF when files are staged) plus the CI check and the `AGENTS.md` rule (4.6). Keep this file anyway for any time the extension or VS Code is used.

Kilo Code (CLI and extension) loads `AGENTS.md` from the project root automatically; the filename must be uppercase. Put the line-ending rule there. A separate Kilo-specific rules file is not required.

Test: run one small Kilo CLI task on Windows (e.g. a one-line edit to `ptos_service.py`) and compare `git diff --stat` with `git diff --stat --ignore-space-at-eol`.

### 4.3 Per-machine git config

On the Windows work machine: `git config core.autocrlf false`. The attributes file takes precedence for normalization, and `autocrlf=true` on top of it is what tends to cause surprises. Android/Termux and Arch need no change.

### 4.4 One-time renormalization commit

Run on a clean working tree, as its own commit with no other changes:

```
git add --renormalize .
git status          # expect only line-ending modifications
git diff --cached --stat --ignore-space-at-eol   # expect empty
git commit -m "Normalize line endings to LF"
```

The empty `--ignore-space-at-eol` diff is the proof that nothing but line endings changed. Re-check the 3 mixed files afterwards; they should now be pure LF.

### 4.5 Blame hygiene

```
git rev-parse HEAD >> .git-blame-ignore-revs
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

Commit `.git-blame-ignore-revs`. Optionally also list `2f9cb5a`, `11d0fa6`, `69f0504`, `2b56814`, `be07621` there so blame skips the CRLF flips.

### 4.6 Guardrail against recurrence

Add a check to CI (and optionally a pre-commit hook):

```
bad=$(git ls-files --eol | grep -v -E 'i/(lf|none|-text)')
[ -z "$bad" ] || { echo "$bad"; echo "Non-LF files found"; exit 1; }
```

Add a rule to `AGENTS.md` / `CLAUDE.md`:

- Write files with LF endings. Never convert a file's line endings as a side effect of an edit.
- Before committing, compare `git diff --stat` with `git diff --stat --ignore-space-at-eol`. If the two differ materially, stop and fix the endings.
- Prefer targeted edits over whole-file rewrites.

## 5. Acceptance criteria

1. `git ls-files --eol` shows no `i/crlf` or `i/mixed` entries at all. `.bat`/`.cmd`/`.ps1` files are stored as `i/lf` in the index and show `w/crlf` in a Windows working tree; that is correct.
2. The renormalize commit has an empty `git diff --ignore-space-at-eol` against its parent.
3. After a fresh clone on Windows, a small edit to `ptos_service.py` produces a diff of only the edited lines.
4. The test suite passes before and after (Python tolerates both endings, but verify).
5. CI fails if a CRLF `.py` file is committed.

## 6. Sequencing with the history purge

You plan to purge personal data from old history before sharing. That rewrite changes every commit hash, so:

1. Do the renormalize commit now (4.1-4.5). It makes day-to-day work clean immediately.
2. Run the purge later. `git filter-repo` can also apply normalization during the rewrite if you want the whole history clean, but that is optional and increases risk; the renormalize commit alone is enough.
3. After the purge, regenerate `.git-blame-ignore-revs` with the new hashes, because the old ones will be stale.
4. Keep your Gmail address in the commit identity during the rewrite, as you decided earlier.

## 7. Risks

- Open PRs or other clones with CRLF edits will conflict after renormalization. The repo has no forks or PRs, so the risk is limited to your own machines: commit and push everywhere first, then use a fresh clone on each (simplest and safest), or `git pull` followed by `git rm --cached -r . && git reset --hard`, which discards uncommitted changes.
- Syncthing: if the working directory is synced across machines, pause sync during the renormalize so a stale CRLF copy is not synced back over the LF files.
- `.bat` files must keep CRLF; the `eol=crlf` attribute above handles that.
