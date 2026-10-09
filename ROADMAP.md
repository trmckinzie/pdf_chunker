# pdf_chunker roadmap

Done when: CI is green on Python 3.12–3.14, and the four sample books split by table of contents or heading detection without falling back to fixed pages.

Tier: code. See `90_Meta/Dev Environment Standard.md` in the dev vault.

## Standardize
- [x] Pin the runtime in `.python-version` (3.14)
- [x] Hash-pinned `requirements*.txt` compiled from `requirements*.in` with uv
- [x] ruff (E, F, I) and `verify.sh` as the one quality entrypoint
- [x] CI on 3.12/3.13/3.14 (3.9 dropped as end-of-life), actions pinned to a SHA, `contents: read`
- [x] `dashboard.json` with `test` and `verify`
- [x] README and CLAUDE.md on the uv + `verify.sh` flow

## Reach done
- [x] All four sample books split without the fixed-page fallback. Checked 2026-10-09 with a dry run: three by embedded TOC, *Thinking, Fast and Slow* by heading + printed-TOC detection
- [x] Committed and pushed as `052c26c`; CI green on 3.12/3.13/3.14 on 2026-10-09. **Done line met.**

## Parked
- [ ] Narrow the two deliberate `except Exception` boundaries (the `fitz.open()` call and the per-chunk write loop) if a stricter ruff profile is ever wanted
