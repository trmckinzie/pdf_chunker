# pdf_chunker

[![CI](https://github.com/trmckinzie/pdf_chunker/actions/workflows/ci.yml/badge.svg)](https://github.com/trmckinzie/pdf_chunker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Split a PDF into one file per chapter — using the book's own structure when it has one, and detecting it from the text when it doesn't.

A naive "every N pages" split cuts files off mid-sentence and mid-argument. This tool looks for the real chapter boundaries first, through whatever signal the PDF actually offers, and only falls back to fixed-size page windows when none of that signal exists.

## How it works

Every PDF is tried against four sources of structure, in order, stopping at the first one that produces a confident result:

1. **Embedded table of contents.** Top-level bookmarks read straight from the PDF's own metadata — the cleanest source, used whenever it exists.
2. **Heading pattern scan.** For PDFs with no bookmarks, each page's opening lines are checked against real chapter conventions — `Chapter 3`, `Part II`, `Prologue`, `Appendix A`, `Notes`, and the like. A heading repeated as a running header on every page of one chapter is recognized and collapsed to its first appearance; the same word used again much later for a genuinely different section is kept as its own entry.
3. **Printed contents-page matching.** Some books render chapter openings with no extractable heading text at all — the chapter number is set as artwork, not text. For those, the tool reads the book's own printed table-of-contents page and searches the rest of the document for where each listed title actually begins.
4. **Fixed-size fallback.** Page windows sized by `--fallback`, used only when nothing above returns a confident result.

Any chapter longer than `--max-chunk` pages is split further into balanced sub-parts — not one full-size piece and a thin leftover.

## Installation

Requires Python 3.12–3.14. Dependencies are managed with [uv](https://docs.astral.sh/uv/) and
locked with hashes in `requirements.txt`.

```bash
git clone https://github.com/trmckinzie/pdf_chunker.git
cd pdf_chunker
uv venv --python 3.14
uv pip install -r requirements.txt --python .venv/bin/python
```

## Usage

```bash
python3 pdf_chunker.py mybook.pdf
```

Output lands in `mybook_Slices/`, one file per chapter: `01-Introduction.pdf`, `02-The_Characters_of_the_Story.pdf`, and so on. Chapters split for size get a `_Part_N` suffix.

Preview the plan before writing anything:

```bash
python3 pdf_chunker.py mybook.pdf --dry-run
```

### Options

| Flag | Default | Description |
|---|---|---|
| `input_pdf` | — | Path to the source PDF (required) |
| `--fallback N` | `15` | Page window size used only when no chapters can be found at all |
| `--max-chunk N` | `30` | Largest chapter allowed before it's split into balanced sub-parts |
| `--output-dir DIR` | `<input_stem>_Slices` next to the source file | Where to write the output |
| `--dry-run` | off | Print the planned chunks without writing any files |
| `--no-detect-chapters` | off | Skip heuristic detection entirely; use fixed `--fallback` windows whenever there's no embedded TOC |

### Examples

```bash
# Cap chapters at 20 pages instead of the default 30
python3 pdf_chunker.py mybook.pdf --max-chunk 20

# Send output somewhere specific
python3 pdf_chunker.py mybook.pdf --output-dir ~/Desktop/chapters

# Force fixed 10-page windows, skipping chapter detection
python3 pdf_chunker.py mybook.pdf --no-detect-chapters --fallback 10
```

## Notes

- Password-protected, corrupted, or empty PDFs are reported with a clear error instead of crashing.
- A chunk that fails to write doesn't stop the rest of the batch — failures are collected and reported at the end.
- Filenames are sanitized for cross-platform safety (illegal characters stripped, length capped) and can never escape the output directory, even from a maliciously crafted PDF.

## Development

```bash
uv venv --python 3.14
uv pip install -r requirements-dev.txt --python .venv/bin/python
bash verify.sh   # ruff + pytest, what CI and pre-push run
```

`requirements.txt` and `requirements-dev.txt` are hash-pinned lockfiles generated from
`requirements.in` and `requirements-dev.in`. Edit the `.in` file, then recompile both:

```bash
uv pip compile requirements.in --universal --generate-hashes --python-version 3.12 -o requirements.txt
uv pip compile requirements-dev.in --universal --generate-hashes --python-version 3.12 -o requirements-dev.txt
```

## License

[MIT](LICENSE)
