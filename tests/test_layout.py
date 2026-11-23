"""Pure layout reconstruction tests - TSV text in, markdown out, no filesystem."""

from __future__ import annotations

from ocr_img.core import (
    build_document,
    markdown_from_tsv,
    parse_tsv,
    summarize_markdown,
)

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)
CHAR_WIDTH = 10  # so a 5-letter word is 50px wide, like real proportional text


def word_row(
    text: str,
    *,
    left: int,
    top: int,
    block: int = 1,
    paragraph: int = 1,
    line: int = 1,
    height: int = 20,
    conf: str = "95.0",
) -> str:
    """Build one level-5 (word) TSV row so tests state only what matters."""
    width = CHAR_WIDTH * max(len(text), 1)
    return (
        f"5\t1\t{block}\t{paragraph}\t{line}\t1\t{left}\t{top}\t{width}\t{height}\t{conf}\t{text}"
    )


def line_of(
    text: str,
    *,
    left: int,
    top: int,
    block: int = 1,
    paragraph: int = 1,
    line: int = 1,
    height: int = 20,
) -> list[str]:
    """Lay a phrase out left-to-right on one TSV line."""
    rows: list[str] = []
    cursor = left
    for token in text.split():
        rows.append(
            word_row(
                token,
                left=cursor,
                top=top,
                block=block,
                paragraph=paragraph,
                line=line,
                height=height,
            )
        )
        cursor += CHAR_WIDTH * len(token) + 8
    return rows


def tsv(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def test_parse_tsv_skips_non_word_rows():
    rows = [
        "1\t1\t0\t0\t0\t0\t0\t0\t900\t420\t-1\t",
        "4\t1\t1\t1\t1\t0\t30\t97\t839\t27\t-1\t",
        word_row("hello", left=30, top=97),
    ]
    assert [w.text for w in parse_tsv(tsv(*rows))] == ["hello"]


def test_parse_tsv_skips_blank_word_text():
    assert parse_tsv(tsv(word_row("", left=0, top=0))) == []


def test_parse_tsv_tolerates_missing_header():
    assert [w.text for w in parse_tsv(word_row("solo", left=10, top=5) + "\n")] == ["solo"]


def test_parse_tsv_ignores_malformed_rows():
    broken = "5\t1\t1\t1\t1\t1\tnot-a-number\t0\t0\t0\t95.0\ttext"
    assert [w.text for w in parse_tsv(tsv(broken, word_row("ok", left=0, top=0)))] == ["ok"]


def test_parse_tsv_reads_confidence_and_box():
    rows = [word_row("word", left=12, top=34, height=18, conf="88.5")]
    cell = parse_tsv(tsv(*rows))[0]
    assert (cell.left, cell.top, cell.height, round(cell.conf, 1)) == (12, 34, 18, 88.5)


def test_wrapped_lines_join_into_one_paragraph():
    rows = [
        *line_of("This paragraph wraps", left=30, top=100, line=1),
        *line_of("onto a second line.", left=30, top=130, line=2),
    ]
    document = markdown_from_tsv(tsv(*rows))
    assert document.text == "This paragraph wraps onto a second line.\n"


def test_hyphenated_wrap_is_rejoined():
    rows = [
        *line_of("recon-", left=30, top=100, line=1),
        *line_of("struction", left=30, top=130, line=2),
    ]
    assert markdown_from_tsv(tsv(*rows)).text == "reconstruction\n"


def test_separate_paragraphs_stay_separate():
    rows = [
        *line_of("First block.", left=30, top=100, block=1, paragraph=1),
        *line_of("Second block.", left=30, top=200, block=2, paragraph=1),
    ]
    assert markdown_from_tsv(tsv(*rows)).text == "First block.\n\nSecond block.\n"


def test_large_type_becomes_h1():
    rows = [
        *line_of("Chapter One", left=30, top=20, block=1, height=48),
        *line_of("Body text follows here.", left=30, top=200, block=2, line=1),
    ]
    document = markdown_from_tsv(tsv(*rows))
    assert document.text == "# Chapter One\n\nBody text follows here.\n"
    assert document.headings == 1


def test_a_lone_heading_is_h1():
    # Heading depth is relative to the page: an image has no absolute levels, so
    # the biggest heading present is `#` whatever its pixel size.
    rows = [
        *line_of("A Section Title", left=30, top=20, block=1, height=28),
        *line_of("Body text follows here.", left=30, top=200, block=2),
    ]
    assert markdown_from_tsv(tsv(*rows)).text.startswith("# A Section Title\n")


def test_a_smaller_heading_under_a_bigger_one_is_h2():
    rows = [
        *line_of("Chapter Title", left=30, top=20, block=1, height=44),
        *line_of("Section Title", left=30, top=120, block=2, height=30),
        *line_of("Body text follows here.", left=30, top=200, block=3),
    ]
    text = markdown_from_tsv(tsv(*rows)).text
    assert text.startswith("# Chapter Title\n")
    assert "\n## Section Title\n" in text


def test_a_heading_similar_in_size_stays_h1():
    rows = [
        *line_of("First Title", left=30, top=20, block=1, height=30),
        *line_of("Second Title", left=30, top=120, block=2, height=30),
        *line_of("Body text follows here.", left=30, top=200, block=3),
    ]
    text = markdown_from_tsv(tsv(*rows)).text
    assert "## Second Title" not in text
    assert text.count("# First Title") == 1


def test_short_standalone_line_becomes_heading():
    rows = [
        *line_of("Introduction", left=30, top=20, block=1),
        *line_of("Body text continues now.", left=30, top=200, block=2, line=1),
        *line_of("and keeps going here.", left=30, top=230, block=2, line=2),
    ]
    document = markdown_from_tsv(tsv(*rows))
    assert document.text.startswith("# Introduction\n")
    assert document.text.endswith("and keeps going here.\n")


def test_sentence_paragraph_is_not_a_heading():
    rows = line_of("This is a full sentence.", left=30, top=100)
    document = markdown_from_tsv(tsv(*rows))
    assert document.text == "This is a full sentence.\n"
    assert document.headings == 0


def test_bullet_lines_become_a_dash_list():
    rows = [
        word_row("-", left=30, top=100, line=1),
        *line_of("first item", left=60, top=100, line=1),
        word_row("-", left=30, top=130, line=2),
        *line_of("second item", left=60, top=130, line=2),
    ]
    document = markdown_from_tsv(tsv(*rows))
    assert document.text == "- first item\n- second item\n"
    assert document.lists == 1


def test_numbered_lines_stay_numbered():
    rows = [
        word_row("1.", left=30, top=100, line=1),
        *line_of("step one", left=70, top=100, line=1),
        word_row("2.", left=30, top=130, line=2),
        *line_of("step two", left=70, top=130, line=2),
    ]
    assert markdown_from_tsv(tsv(*rows)).text == "1. step one\n2. step two\n"


def test_nested_bullet_is_indented():
    rows = [
        word_row("-", left=30, top=100, line=1),
        *line_of("outer item", left=60, top=100, line=1),
        word_row("-", left=54, top=130, line=2),
        *line_of("nested item", left=84, top=130, line=2),
    ]
    document = markdown_from_tsv(tsv(*rows))
    assert document.text == "- outer item\n  - nested item\n"


def test_prose_is_not_turned_into_a_list():
    rows = line_of("Plain prose without bullets.", left=30, top=100)
    document = markdown_from_tsv(tsv(*rows))
    assert document.lists == 0
    assert document.text == "Plain prose without bullets.\n"


def test_wrapped_list_item_joins_its_marker():
    rows = [
        word_row("-", left=30, top=100, line=1),
        *line_of("an item that wraps", left=60, top=100, line=1),
        *line_of("onto a second line", left=60, top=130, line=2),
    ]
    assert markdown_from_tsv(tsv(*rows)).text == "- an item that wraps onto a second line\n"


def test_markdown_syntax_in_text_is_escaped():
    rows = line_of("a_b*c sentence.", left=30, top=100)
    assert markdown_from_tsv(tsv(*rows)).text == "a\\_b\\*c sentence.\n"


def test_empty_tsv_yields_empty_markdown():
    assert markdown_from_tsv("").text == ""
    assert markdown_from_tsv(tsv()).text == ""


def test_build_document_is_deterministic():
    rows = [
        word_row("beta", left=90, top=100),
        word_row("alpha", left=30, top=100),
    ]
    first = build_document(parse_tsv(tsv(*rows)))
    second = build_document(parse_tsv(tsv(*rows)))
    assert first == second
    assert first.lines[0].text == "alpha beta"


def test_summarize_reports_counts():
    rows = [word_row("Solo", left=30, top=100)]
    summary = summarize_markdown(markdown_from_tsv(tsv(*rows)))
    assert "markdown" in summary
    assert "headings" in summary
    assert "lists" in summary


# --- regression tests from real multi-heading / multi-list documents --------


def test_body_type_survives_a_page_full_of_headings():
    # Three headings, one body paragraph: a median of word heights would land in
    # a heading band and then misread every heading on the page.
    rows = [
        *line_of("Main Title Here", left=40, top=20, block=1, height=44),
        *line_of("First Section", left=40, top=110, block=2, height=30),
        *line_of("Body words used for measurement.", left=40, top=160, block=3, line=1),
        *line_of("More body words continue here.", left=40, top=190, block=3, line=2),
        *line_of("Second Section", left=40, top=250, block=4, height=30),
    ]
    text = markdown_from_tsv(tsv(*rows)).text
    assert text.startswith("# Main Title Here\n")
    assert "## First Section" in text
    assert "## Second Section" in text
    assert "Body words used for measurement. More body words continue here." in text


def test_separate_lists_at_similar_offsets_are_not_nested():
    # Two lists in different blocks whose markers differ by a few pixels. A
    # page-wide frame of reference reads that as one nested list.
    rows = [
        word_row("1.", left=57, top=100, block=1, line=1),
        *line_of("first", left=87, top=100, block=1, line=1),
        word_row("2.", left=57, top=130, block=1, line=2),
        *line_of("second", left=87, top=130, block=1, line=2),
        word_row("-", left=56, top=200, block=2, line=1),
        *line_of("alpha", left=86, top=200, block=2, line=1),
        word_row("-", left=56, top=230, block=2, line=2),
        *line_of("beta", left=86, top=230, block=2, line=2),
    ]
    text = markdown_from_tsv(tsv(*rows)).text
    assert text == "1. first\n2. second\n\n- alpha\n- beta\n"


def test_real_nesting_is_preserved_next_to_a_flat_list():
    rows = [
        word_row("-", left=55, top=100, block=1, line=1),
        *line_of("flat item", left=85, top=100, block=1, line=1),
        word_row("-", left=55, top=130, block=1, line=2),
        *line_of("parent item", left=85, top=130, block=1, line=2),
        word_row("-", left=95, top=160, block=1, line=3),
        *line_of("child item", left=125, top=160, block=1, line=3),
    ]
    text = markdown_from_tsv(tsv(*rows)).text
    assert text == "- flat item\n- parent item\n  - child item\n"
