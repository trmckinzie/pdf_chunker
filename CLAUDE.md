# pdf_chunker — session notes

See [README.md](README.md) for how the four-source detection cascade works. The ordering is the
design: a threshold change that fixes one book routinely breaks others, so evaluate across the
fixture set and report what regressed, not only what improved. CI runs on this repo — keep it green.

## Model routing

Sonnet executes, Opus escalates, Fable only on Travis's explicit say-so. This repo's subagents
live in `.claude/agents/`; the doctrine they point to is `90_Meta/Model Routing.md` in the dev
mono-vault containing this repo — personal workflow config, not part of this project.
