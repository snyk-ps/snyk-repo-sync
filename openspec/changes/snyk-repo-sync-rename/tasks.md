## 1. Fix Python 3.12 import bug

- [ ] 1.1 Add `from __future__ import annotations` as the first line of `src/config/scope_mapping.py`
- [ ] 1.2 Verify import under Python 3.12: `docker build` + `docker run ... --help`, or equivalent Python 3.12 import check
- [ ] 1.3 Run `uv run pytest tests/config/test_scope_mapping.py -q`

## 2. Rename application and package

- [ ] 2.1 Rename `pyproject.toml` `[project].name` to `snyk-repo-sync`; run `uv lock`
- [ ] 2.2 Confirm `.github/workflows/release.yml` publishes to `ghcr.io/snyk-ps/snyk-repo-sync:<tag>` (via `github.repository` or explicit tag); update if still referencing old repo name
- [ ] 2.3 Update user-facing name to **Snyk Repo Sync** in README.md, CONTRIBUTING.md, and `data/DESIGN.md`; update GitHub repo links to `github.com/snyk-ps/snyk-repo-sync`

## 3. README restructure and GHCR reference

- [ ] 3.1 Move **Deployment** section (and its subsections) to immediately follow intro + TOC
- [ ] 3.2 Rename **Installation and setup** → **Local development**; move to bottom (before **More documentation**)
- [ ] 3.3 Remove duplicate **Deployment / production installation** checklist from local section; link to top **Deployment** section
- [ ] 3.4 Replace generic `ghcr.io/<owner>/<repository>:<tag>` with `ghcr.io/snyk-ps/snyk-repo-sync:<version>` in Deployment (intro, step C, troubleshooting, production install pointer)
- [ ] 3.5 Update TOC anchors to match new section order
- [ ] 3.6 Update CONTRIBUTING.md GHCR examples to reference `ghcr.io/snyk-ps/snyk-repo-sync:<tag>` where operator-facing

## 4. Quality

- [ ] 4.1 Grep for remaining `snyk-azure-repo-sync` / `Snyk Azure Repo Sync` strings; update all to `snyk-repo-sync` / **Snyk Repo Sync** (GitHub repo already renamed)
- [ ] 4.2 Confirm no Container App Job or Boards-specific regression in reordered README

## 5. OpenSpec archive

- [ ] 5.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/snyk-repo-sync-rename/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive snyk-repo-sync-rename` after review and merge
