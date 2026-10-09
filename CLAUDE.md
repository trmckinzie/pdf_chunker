# pdf_chunker — session notes

See [README.md](README.md) for how the four-source detection cascade works. The ordering is the
design: a threshold change that fixes one book routinely breaks others, so evaluate across the
fixture set and report what regressed, not only what improved. CI runs on this repo — keep it green.

## Setup and verification

```bash
uv venv --python 3.14
uv pip install -r requirements-dev.txt --python .venv/bin/python
bash verify.sh
```

`verify.sh` runs ruff then pytest — the same checks CI runs on push/PR (Python 3.12–3.14) and
what the pre-push hook runs as a warning. `requirements.txt` / `requirements-dev.txt` are
hash-pinned, generated from `requirements.in` / `requirements-dev.in` with `uv pip compile
--universal --generate-hashes --python-version 3.12`; never hand-edit the compiled `.txt` files.

## Model routing

Sonnet executes, Opus escalates, Fable only on Travis's explicit say-so. This repo's subagents
live in `.claude/agents/`; the doctrine they point to is `90_Meta/Model Routing.md` in the dev
mono-vault containing this repo — personal workflow config, not part of this project.
