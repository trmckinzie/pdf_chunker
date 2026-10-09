import argparse

import fitz
import pytest

import pdf_chunker as pc


def make_pdf(path, page_headers=None, toc=None, page_count=None):
    """Build a small PDF for tests. page_headers maps 0-indexed page -> lines of text."""
    doc = fitz.open()
    total = page_count or (max(page_headers) + 1 if page_headers else 1)
    for i in range(total):
        page = doc.new_page()
        for j, line in enumerate((page_headers or {}).get(i, [])):
            page.insert_text((72, 40 + j * 20), line)
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()


# --- positive_int ---

def test_positive_int_accepts_positive_values():
    assert pc.positive_int("5") == 5
    assert pc.positive_int("1") == 1


@pytest.mark.parametrize("value", ["0", "-3", "abc", "1.5"])
def test_positive_int_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        pc.positive_int(value)


# --- sanitize_filename ---

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Chapter 1: Intro/Overview?", "Chapter_1_IntroOverview"),
        ("A*B\\C Test", "ABC_Test"),
        ("../../../../etc/passwd", "etcpasswd"),
        ("..\\..\\Windows\\System32\\evil", "WindowsSystem32evil"),
        ("/etc/passwd", "etcpasswd"),
        ("", "Untitled"),
        ("   ", "Untitled"),
        ("...", "Untitled"),
        ("Multiple   Spaces", "Multiple_Spaces"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert pc.sanitize_filename(raw) == expected


def test_sanitize_filename_never_contains_path_separators():
    result = pc.sanitize_filename("a/b\\c")
    assert "/" not in result
    assert "\\" not in result


def test_sanitize_filename_truncates_long_titles():
    result = pc.sanitize_filename("a" * 500)
    assert len(result) == pc.MAX_TITLE_LENGTH


def test_sanitize_filename_custom_fallback():
    assert pc.sanitize_filename("???", fallback="Chapter") == "Chapter"


# --- split_range ---

def test_split_range_returns_single_range_when_under_limit():
    assert pc.split_range(0, 9, 30) == [(0, 9)]


def test_split_range_splits_evenly():
    # 20 pages, max 10 -> two balanced 10-page parts
    assert pc.split_range(0, 19, 10) == [(0, 9), (10, 19)]


def test_split_range_balances_remainder():
    # 35 pages, max 30 -> 2 parts, balanced ~17/18 not 30/5
    parts = pc.split_range(0, 34, 30)
    assert len(parts) == 2
    sizes = [end - start + 1 for start, end in parts]
    assert sizes == [18, 17]
    assert max(sizes) <= 30


def test_split_range_covers_every_page_with_no_gaps_or_overlaps():
    parts = pc.split_range(5, 104, 30)
    assert parts[0][0] == 5
    assert parts[-1][1] == 104
    for (_, end), (next_start, _) in zip(parts, parts[1:]):
        assert next_start == end + 1


# --- calculate_page_ranges ---

def test_calculate_page_ranges_rejects_nonpositive_settings():
    with pytest.raises(ValueError):
        pc.calculate_page_ranges([], 10, fallback=0, max_chunk=30)
    with pytest.raises(ValueError):
        pc.calculate_page_ranges([], 10, fallback=15, max_chunk=0)


def test_calculate_page_ranges_from_toc():
    toc = [
        {"title": "Intro", "start_page": 0},
        {"title": "Middle", "start_page": 5},
        {"title": "End", "start_page": 12},
    ]
    ranges = pc.calculate_page_ranges(toc, total_pages=20, fallback=15, max_chunk=30)
    assert ranges == [
        ("01-Intro.pdf", 0, 4),
        ("02-Middle.pdf", 5, 11),
        ("03-End.pdf", 12, 19),
    ]


def test_calculate_page_ranges_splits_oversized_chapter():
    toc = [{"title": "Big", "start_page": 0}]
    ranges = pc.calculate_page_ranges(toc, total_pages=35, fallback=15, max_chunk=30)
    names = [r[0] for r in ranges]
    assert names == ["01-Big_Part_1.pdf", "01-Big_Part_2.pdf"]


def test_calculate_page_ranges_fallback_when_no_toc():
    ranges = pc.calculate_page_ranges([], total_pages=37, fallback=15, max_chunk=30)
    assert ranges == [
        ("001-Pages_1-15.pdf", 0, 14),
        ("002-Pages_16-30.pdf", 15, 29),
        ("003-Pages_31-37.pdf", 30, 36),
    ]


def test_calculate_page_ranges_output_is_sorted_by_start_page():
    toc = [{"title": "B", "start_page": 5}, {"title": "A", "start_page": 0}]
    ranges = pc.calculate_page_ranges(toc, total_pages=10, fallback=15, max_chunk=30)
    starts = [r[1] for r in ranges]
    assert starts == sorted(starts)


# --- merge_chapter_lists ---

def test_merge_chapter_lists_keeps_distinct_nearby_headings():
    a = [{"title": "Part_5", "start_page": 10}]
    b = [{"title": "Two_Selves", "start_page": 11}]
    merged = pc.merge_chapter_lists(a, b)
    assert len(merged) == 2


def test_merge_chapter_lists_drops_near_duplicate_same_title():
    a = [{"title": "Notes", "start_page": 10}]
    b = [{"title": "Notes", "start_page": 11}]
    merged = pc.merge_chapter_lists(a, b)
    assert len(merged) == 1


def test_merge_chapter_lists_keeps_same_title_far_apart():
    a = [{"title": "Notes", "start_page": 10}]
    b = [{"title": "Notes", "start_page": 200}]
    merged = pc.merge_chapter_lists(a, b)
    assert len(merged) == 2


# --- normalize_heading ---

def test_normalize_heading_collapses_whitespace_and_case():
    assert pc.normalize_heading("  Two   Selves  ") == "two selves"


def test_normalize_heading_strips_trailing_period():
    assert pc.normalize_heading("Introduction.") == "introduction"


def test_normalize_heading_normalizes_curly_quotes():
    assert pc.normalize_heading("Tom W’s Specialty") == "tom w's specialty"


# --- resolve_output_dir ---

def test_resolve_output_dir_default(tmp_path):
    input_path = tmp_path / "mybook.pdf"
    assert pc.resolve_output_dir(input_path) == tmp_path / "mybook_Slices"


def test_resolve_output_dir_override(tmp_path):
    input_path = tmp_path / "mybook.pdf"
    override = tmp_path / "custom"
    assert pc.resolve_output_dir(input_path, override) == override


# --- extract_toc ---

def test_extract_toc_keeps_only_top_level_entries(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    make_pdf(
        pdf_path,
        page_count=5,
        toc=[[1, "Chapter 1", 1], [2, "Nested section", 1], [1, "Chapter 2", 3]],
    )
    doc = fitz.open(str(pdf_path))
    toc = pc.extract_toc(doc)
    doc.close()
    assert [c["title"] for c in toc] == ["Chapter_1", "Chapter_2"]


def test_extract_toc_drops_invalid_page_numbers():
    # PyMuPDF's own writer silently normalizes out-of-range TOC targets on save,
    # so this guard is exercised with a minimal fake doc instead of a real file.
    class FakeDoc:
        page_count = 3

        def get_toc(self, simple=True):
            return [[1, "Too low", 0], [1, "Too high", 99], [1, "Good", 1]]

    toc = pc.extract_toc(FakeDoc())
    assert [c["title"] for c in toc] == ["Good"]


# --- detect_chapter_headings ---

def test_detect_chapter_headings_collapses_running_headers(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    headers = {}
    for i in range(5):
        headers[i] = ["Chapter 1"] + (["The Beginning"] if i == 0 else [])
    for i in range(5, 12):
        headers[i] = ["Chapter 2"] + (["Rising Action"] if i == 5 else [])
    make_pdf(pdf_path, page_headers=headers, page_count=12)
    doc = fitz.open(str(pdf_path))
    chapters = pc.detect_chapter_headings(pc.extract_page_lines(doc))
    doc.close()
    assert [c["start_page"] for c in chapters] == [0, 5]
    assert chapters[0]["title"] == "Chapter_1_The_Beginning"


def test_detect_chapter_headings_ignores_body_text_mentions(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    headers = {i: [f"As discussed in chapter {i}, results were significant."] for i in range(10)}
    make_pdf(pdf_path, page_headers=headers, page_count=10)
    doc = fitz.open(str(pdf_path))
    chapters = pc.detect_chapter_headings(pc.extract_page_lines(doc))
    doc.close()
    assert chapters == []


def test_detect_chapter_headings_requires_minimum_count(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    make_pdf(pdf_path, page_headers={0: ["Chapter 1"]}, page_count=10)
    doc = fitz.open(str(pdf_path))
    chapters = pc.detect_chapter_headings(pc.extract_page_lines(doc))
    doc.close()
    assert chapters == []


# --- find_contents_pages / detect_chapters_from_text_toc ---

def test_find_contents_pages_stops_at_prose(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    headers = {
        0: ["Contents", "1. First Chapter", "2. Second Chapter"],
        1: [
            "First Chapter",
            "This is a long line of ordinary prose that runs well past the short-entry "
            "length threshold used to detect contents pages.",
        ],
    }
    make_pdf(pdf_path, page_headers=headers, page_count=2)
    doc = fitz.open(str(pdf_path))
    contents_pages = pc.find_contents_pages(pc.extract_page_lines(doc))
    doc.close()
    assert contents_pages == [0]


def test_detect_chapters_from_text_toc_matches_titles_to_pages(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    headers = {
        0: ["Contents", "1. First Chapter", "2. Second Chapter"],
        3: ["First Chapter", "Body text starts here."],
        9: ["Second Chapter", "More body text."],
    }
    make_pdf(pdf_path, page_headers=headers, page_count=15)
    doc = fitz.open(str(pdf_path))
    page_lines = pc.extract_page_lines(doc)
    contents_pages = pc.find_contents_pages(page_lines)
    chapters = pc.detect_chapters_from_text_toc(page_lines, contents_pages)
    doc.close()
    assert [(c["title"], c["start_page"]) for c in chapters] == [
        ("First_Chapter", 3),
        ("Second_Chapter", 9),
    ]


# --- generate_pdf_chunks ---

def test_generate_pdf_chunks_dry_run_writes_nothing(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    make_pdf(pdf_path, page_count=10)
    doc = fitz.open(str(pdf_path))
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    generated, failures, skipped = pc.generate_pdf_chunks(
        doc, output_dir, [("01-Chapter.pdf", 0, 9)], dry_run=True
    )
    doc.close()
    assert failures == []
    assert skipped == []
    assert generated == [(output_dir / "01-Chapter.pdf", 10, None)]
    assert not (output_dir / "01-Chapter.pdf").exists()


def test_generate_pdf_chunks_writes_correct_page_ranges(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    headers = {i: [f"Page {i + 1}"] for i in range(20)}
    make_pdf(pdf_path, page_headers=headers, page_count=20)
    doc = fitz.open(str(pdf_path))
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    ranges = [("01-First.pdf", 0, 9), ("02-Second.pdf", 10, 19)]
    generated, failures, skipped = pc.generate_pdf_chunks(doc, output_dir, ranges, dry_run=False)
    doc.close()

    assert failures == []
    assert skipped == []
    assert len(generated) == 2

    first = fitz.open(str(output_dir / "01-First.pdf"))
    assert first.page_count == 10
    assert first[0].get_text().strip() == "Page 1"
    first.close()

    second = fitz.open(str(output_dir / "02-Second.pdf"))
    assert second.page_count == 10
    assert second[0].get_text().strip() == "Page 11"
    second.close()


def test_generate_pdf_chunks_does_not_overwrite_existing_file_without_force(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    make_pdf(pdf_path, page_count=10)
    doc = fitz.open(str(pdf_path))
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    target = output_dir / "01-Chapter.pdf"
    target.write_bytes(b"pre-existing content, not a real pdf")
    original_bytes = target.read_bytes()

    generated, failures, skipped = pc.generate_pdf_chunks(
        doc, output_dir, [("01-Chapter.pdf", 0, 9)], dry_run=False, force=False
    )
    doc.close()

    assert failures == []
    assert generated == []
    assert skipped == [target]
    assert target.read_bytes() == original_bytes


def test_generate_pdf_chunks_overwrites_existing_file_with_force(tmp_path):
    pdf_path = tmp_path / "book.pdf"
    make_pdf(pdf_path, page_count=10)
    doc = fitz.open(str(pdf_path))
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    target = output_dir / "01-Chapter.pdf"
    target.write_bytes(b"pre-existing content, not a real pdf")

    generated, failures, skipped = pc.generate_pdf_chunks(
        doc, output_dir, [("01-Chapter.pdf", 0, 9)], dry_run=False, force=True
    )
    doc.close()

    assert failures == []
    assert skipped == []
    assert len(generated) == 1
    assert target.read_bytes() != b"pre-existing content, not a real pdf"
