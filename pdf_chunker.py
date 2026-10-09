import argparse
import math
import re
import sys
from pathlib import Path

import fitz

TOC_TOP_LEVEL = 1
MAX_TITLE_LENGTH = 150
ILLEGAL_CHARS_RE = re.compile(r'[:/\\?*"<>|\x00-\x1f]')

NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    "fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
)
CHAPTER_HEADING_RE = re.compile(
    r'^(chapter|part|book)\s+(\d{1,3}|[ivxlcdm]{1,7}|' + NUMBER_WORDS + r')\b',
    re.IGNORECASE,
)
SECTION_HEADING_RE = re.compile(
    r'^(prologue|epilogue|introduction|preface|foreword|afterword|conclusion|'
    r'acknowledgments|acknowledgements|notes|references|bibliography|index|glossary)\s*$',
    re.IGNORECASE,
)
APPENDIX_HEADING_RE = re.compile(r'^appendix(\s+[a-z0-9]+)?\b', re.IGNORECASE)
HEADING_SCAN_LINES = 6
HEADING_MAX_LINE_LENGTH = 100
MIN_DETECTED_CHAPTERS = 2
MIN_AVG_CHAPTER_GAP = 3
RUNNING_HEADER_GAP = 3

CONTENTS_TITLE_RE = re.compile(r'^(table of contents|contents)$', re.IGNORECASE)
NUMBERED_ENTRY_RE = re.compile(r'^\d{1,3}[.)]\s*(.+)$')
MAX_CONTENTS_SCAN_PAGES = 20
MAX_CONTENTS_BLOCK_PAGES = 6
TOC_ENTRY_MAX_LEN = 45
TOC_PAGE_MATCH_RATIO = 0.7
SUBTITLE_MAX_WORDS = 8
SUBTITLE_MAX_LENGTH = 50
SUBTITLE_MIN_CAPITALIZED_RATIO = 0.6
QUOTE_TRANSLATION = str.maketrans('“”‘’', '""\'\'')


def positive_int(value):
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not an integer")
    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"'{value}' must be a positive integer")
    return ivalue


def sanitize_filename(text, fallback="Untitled"):
    text = ILLEGAL_CHARS_RE.sub('', text)
    text = text.strip().replace(' ', '_')
    text = re.sub(r'_+', '_', text)
    text = text.strip('._')
    text = text[:MAX_TITLE_LENGTH]
    return text or fallback


def extract_toc(doc):
    total_pages = doc.page_count
    chapters = []
    for level, title, page in doc.get_toc(simple=True):
        if level != TOC_TOP_LEVEL:
            continue
        if page < 1 or page > total_pages:
            continue
        chapters.append({"title": sanitize_filename(title), "start_page": page - 1})
    return chapters


def extract_page_lines(doc):
    return [
        [ln.strip() for ln in doc[i].get_text().splitlines() if ln.strip()]
        for i in range(doc.page_count)
    ]


def normalize_heading(text):
    text = text.translate(QUOTE_TRANSLATION)
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text.rstrip('.')


def _looks_like_toc_entry(line):
    return bool(
        NUMBERED_ENTRY_RE.match(line)
        or CHAPTER_HEADING_RE.match(line)
        or SECTION_HEADING_RE.match(line)
        or APPENDIX_HEADING_RE.match(line)
        or len(line) <= TOC_ENTRY_MAX_LEN
    )


def _looks_like_subtitle(line):
    words = line.split()
    if not (1 <= len(words) <= SUBTITLE_MAX_WORDS) or len(line) >= SUBTITLE_MAX_LENGTH:
        return False
    cap_words = 0
    for word in words:
        letters = [ch for ch in word if ch.isalpha()]
        if letters and letters[0].isupper():
            cap_words += 1
    return cap_words / len(words) >= SUBTITLE_MIN_CAPITALIZED_RATIO


def find_contents_pages(page_lines):
    limit = min(MAX_CONTENTS_SCAN_PAGES, len(page_lines))
    start = None
    for page_index in range(limit):
        lines = page_lines[page_index]
        if lines and CONTENTS_TITLE_RE.match(lines[0]):
            start = page_index
            break
    if start is None:
        return []

    pages = [start]
    for page_index in range(start + 1, min(start + MAX_CONTENTS_BLOCK_PAGES, len(page_lines))):
        lines = page_lines[page_index]
        if len(lines) < 3:
            break
        toc_like = sum(1 for ln in lines if _looks_like_toc_entry(ln))
        if toc_like / len(lines) < TOC_PAGE_MATCH_RATIO:
            break
        pages.append(page_index)
    return pages


def detect_chapter_headings(page_lines, skip_pages=()):
    skip = set(skip_pages)
    candidates = []
    last_occurrence_page = {}

    for page_index, lines in enumerate(page_lines):
        if page_index in skip:
            continue
        for idx, line in enumerate(lines[:HEADING_SCAN_LINES]):
            if len(line) > HEADING_MAX_LINE_LENGTH:
                continue
            match = (
                CHAPTER_HEADING_RE.match(line)
                or SECTION_HEADING_RE.match(line)
                or APPENDIX_HEADING_RE.match(line)
            )
            if not match:
                continue

            key = re.sub(r'\s+', ' ', match.group(0).lower())
            prev_page = last_occurrence_page.get(key)
            is_new_heading = prev_page is None or page_index - prev_page >= RUNNING_HEADER_GAP
            last_occurrence_page[key] = page_index
            if not is_new_heading:
                break

            title = line
            if len(line) - len(match.group(0)) < 2 and idx + 1 < len(lines):
                next_line = lines[idx + 1]
                if _looks_like_subtitle(next_line):
                    title = f"{line} {next_line}"

            candidates.append((page_index, title))
            break

    if len(candidates) < MIN_DETECTED_CHAPTERS:
        return []

    if len(page_lines) / len(candidates) < MIN_AVG_CHAPTER_GAP:
        return []

    return [
        {"title": sanitize_filename(title), "start_page": page_index}
        for page_index, title in candidates
    ]


def detect_chapters_from_text_toc(page_lines, contents_pages):
    if not contents_pages:
        return []

    candidates = []
    for page_index in contents_pages:
        for line in page_lines[page_index]:
            if CONTENTS_TITLE_RE.match(line):
                continue
            match = NUMBERED_ENTRY_RE.match(line)
            if not match:
                continue
            title = match.group(1).strip()
            if len(title) >= 3:
                candidates.append(title)

    if len(candidates) < MIN_DETECTED_CHAPTERS:
        return []

    normalized_candidates = [normalize_heading(t) for t in candidates]

    matches = []
    pointer = 0
    scan_start = max(contents_pages) + 1
    for page_index in range(scan_start, len(page_lines)):
        if pointer >= len(candidates):
            break
        lines = page_lines[page_index]
        if lines and normalize_heading(lines[0]) == normalized_candidates[pointer]:
            matches.append((page_index, candidates[pointer]))
            pointer += 1

    if len(matches) < MIN_DETECTED_CHAPTERS:
        return []

    if len(page_lines) / len(matches) < MIN_AVG_CHAPTER_GAP:
        return []

    return [
        {"title": sanitize_filename(title), "start_page": page_index}
        for page_index, title in matches
    ]


def merge_chapter_lists(chapters_a, chapters_b, min_gap=2):
    combined = sorted(chapters_a + chapters_b, key=lambda c: c["start_page"])
    merged = []
    for chapter in combined:
        if merged:
            prev = merged[-1]
            close = chapter["start_page"] - prev["start_page"] < min_gap
            same_title = normalize_heading(chapter["title"]) == normalize_heading(prev["title"])
            if close and same_title:
                continue
        merged.append(chapter)
    return merged


def detect_toc_less_chapters(doc):
    page_lines = extract_page_lines(doc)
    contents_pages = find_contents_pages(page_lines)

    regex_chapters = detect_chapter_headings(page_lines, skip_pages=contents_pages)
    text_toc_chapters = detect_chapters_from_text_toc(page_lines, contents_pages)

    if regex_chapters and text_toc_chapters:
        return (
            merge_chapter_lists(regex_chapters, text_toc_chapters),
            "combined heading and table-of-contents detection",
        )
    if text_toc_chapters:
        return text_toc_chapters, "its printed table of contents"
    if regex_chapters:
        return regex_chapters, "detected chapter headings"
    return [], None


def resolve_output_dir(input_path, override=None):
    if override:
        return Path(override)
    return input_path.parent / f"{input_path.stem}_Slices"


def split_range(start, end, max_chunk):
    length = end - start + 1
    if length <= max_chunk:
        return [(start, end)]

    num_parts = math.ceil(length / max_chunk)
    base_size, remainder = divmod(length, num_parts)

    parts = []
    cursor = start
    for i in range(num_parts):
        size = base_size + (1 if i < remainder else 0)
        part_end = cursor + size - 1
        parts.append((cursor, part_end))
        cursor = part_end + 1
    return parts


def calculate_page_ranges(toc, total_pages, fallback, max_chunk):
    if fallback < 1 or max_chunk < 1:
        raise ValueError("--fallback and --max-chunk must be positive integers")

    ranges = []

    if toc:
        pad = max(2, len(str(len(toc))))
        for i, chapter in enumerate(toc):
            start = chapter["start_page"]
            end = toc[i + 1]["start_page"] - 1 if i + 1 < len(toc) else total_pages - 1
            end = max(end, start)

            sub_ranges = split_range(start, end, max_chunk)
            total_parts = len(sub_ranges)
            for part_num, (sub_start, sub_end) in enumerate(sub_ranges, start=1):
                suffix = f"_Part_{part_num}" if total_parts > 1 else ""
                filename = f"{i + 1:0{pad}d}-{chapter['title']}{suffix}.pdf"
                ranges.append((filename, sub_start, sub_end))
    else:
        total_chunks = math.ceil(total_pages / fallback)
        pad = max(3, len(str(total_chunks)))
        index = 1
        start = 0
        while start < total_pages:
            end = min(start + fallback - 1, total_pages - 1)
            filename = f"{index:0{pad}d}-Pages_{start + 1}-{end + 1}.pdf"
            ranges.append((filename, start, end))
            start = end + 1
            index += 1

    ranges.sort(key=lambda r: r[1])
    return ranges


def generate_pdf_chunks(src_doc, output_dir, page_ranges, dry_run=False, force=False):
    generated = []
    failures = []
    skipped = []

    for filename, start, end in page_ranges:
        output_path = output_dir / filename
        page_count = end - start + 1

        if dry_run:
            generated.append((output_path, page_count, None))
            continue

        if output_path.exists() and not force:
            skipped.append(output_path)
            continue

        try:
            chunk_doc = fitz.open()
            chunk_doc.insert_pdf(src_doc, from_page=start, to_page=end)
            chunk_doc.save(str(output_path))
            chunk_doc.close()
            generated.append((output_path, page_count, output_path.stat().st_size))
        except Exception as exc:
            failures.append((filename, str(exc)))

    return generated, failures, skipped


def parse_args():
    parser = argparse.ArgumentParser(
        description="Split a PDF into per-chapter files using its table of contents."
    )
    parser.add_argument("input_pdf", help="Path to the input PDF file")
    parser.add_argument(
        "--fallback",
        type=positive_int,
        default=15,
        help="Fallback chunk size in pages, used when the PDF has no usable TOC (default: 15)",
    )
    parser.add_argument(
        "--max-chunk",
        type=positive_int,
        default=30,
        help="Maximum chapter size in pages before it gets split further (default: 30)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory to save the output chunks "
            "(default: '<input_stem>_Slices' next to the source PDF)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the planned chunks without writing any files",
    )
    parser.add_argument(
        "--no-detect-chapters",
        action="store_true",
        help="Disable heuristic chapter-heading detection; use fixed-size --fallback windows "
        "when the PDF has no embedded TOC",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output files that already exist (default: skip them with a warning)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    input_path = Path(args.input_pdf)
    if not input_path.is_file():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        src_doc = fitz.open(str(input_path))
    except Exception as exc:
        print(f"Error: could not open '{input_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    if src_doc.needs_pass:
        print(
            f"Error: '{input_path}' is password-protected and cannot be processed.",
            file=sys.stderr,
        )
        src_doc.close()
        sys.exit(1)

    total_pages = src_doc.page_count
    if total_pages == 0:
        print(f"Error: '{input_path}' has no pages.", file=sys.stderr)
        src_doc.close()
        sys.exit(1)

    toc = extract_toc(src_doc)
    detection_method = None
    if not toc and not args.no_detect_chapters:
        toc, detection_method = detect_toc_less_chapters(src_doc)

    try:
        page_ranges = calculate_page_ranges(toc, total_pages, args.fallback, args.max_chunk)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        src_doc.close()
        sys.exit(1)

    output_dir = resolve_output_dir(input_path, args.output_dir)
    if not args.dry_run:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(
                f"Error: could not create output directory '{output_dir}': {exc}",
                file=sys.stderr,
            )
            src_doc.close()
            sys.exit(1)

        existing = list(output_dir.glob("*.pdf"))
        if existing:
            print(
                f"Warning: '{output_dir}' already contains {len(existing)} PDF file(s) "
                "from a previous run; stale files with names that no longer match this "
                "run will be left in place.",
                file=sys.stderr,
            )

    mode = "[DRY RUN] " if args.dry_run else ""
    if detection_method:
        source = f"{len(toc)} chapters found via {detection_method} (no embedded TOC found)"
    elif toc:
        source = "its table of contents"
    else:
        source = f"{args.fallback}-page fallback windows (no usable TOC or chapter headings found)"
    print(f"{mode}Splitting '{input_path.name}' ({total_pages} pages) using {source}")

    generated, failures, skipped = generate_pdf_chunks(
        src_doc, output_dir, page_ranges, dry_run=args.dry_run, force=args.force
    )
    src_doc.close()

    verb = "Would generate" if args.dry_run else "Generated"
    print(f"\n{verb} {len(generated)} file(s) in {output_dir}:")
    total_size = 0
    for output_path, page_count, size in generated:
        label = "page" if page_count == 1 else "pages"
        if size is None:
            print(f"  {output_path.name}  ({page_count} {label})")
        else:
            total_size += size
            print(f"  {output_path.name}  ({page_count} {label}, {size / 1024:.1f} KB)")

    if total_size:
        print(f"\nTotal output size: {total_size / 1024:.1f} KB")

    if skipped:
        print(
            f"\n{len(skipped)} file(s) skipped because they already exist "
            "(use --force to overwrite):",
            file=sys.stderr,
        )
        for output_path in skipped:
            print(f"  {output_path.name}", file=sys.stderr)

    if failures:
        print(f"\n{len(failures)} file(s) failed to write:", file=sys.stderr)
        for filename, error in failures:
            print(f"  {filename}: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
