"""Recovery of D8 files from a job log must verify everything or write nothing.

The emitter (``evals.d8_report.emit``) and the reader (``evals.d8_recover``) are tested
against each other, including the awkward inputs: no trailing newline, an empty file,
content lines that look like markers or like timestamps, GitHub's timestamp prefixes,
CRLF endings, and logs without prefixes. Every refusal rule has its own test and
asserts that nothing was written.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from evals import d8_recover, d8_report

FAKE_DIGEST = "0" * 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def block(path: str, content: bytes, *, digest: str | None = None, size: int | None = None) -> str:
    """One BEGIN/END block exactly as the emitter writes it."""
    digest = digest or sha(content)
    size = len(content) if size is None else size
    return f"D8-FILE-BEGIN {path} {digest} {size}\n{content.decode('utf-8')}\nD8-FILE-END {path}\n"


def stamp(text: str, *, crlf: bool = False, bare_empty: bool = False) -> str:
    """Prefix every line the way the job-log API does."""
    lines = text.split("\n")
    out = []
    for number, line in enumerate(lines):
        if line == "" and number == len(lines) - 1:
            out.append("")  # the text's own final newline
            continue
        prefix = f"2026-11-12T10:11:{number % 60:02d}.1234567Z"
        out.append(prefix if (line == "" and bare_empty) else f"{prefix} {line}")
    return ("\r\n" if crlf else "\n").join(out)


AWKWARD: dict[str, bytes] = {
    "plain.json": b'{"a": 1}\n',
    "no-newline.txt": b"last line has no newline",
    "empty.txt": b"",
    "blank-lines.txt": b"\n\nx\n\n",
    "unicode/한글.md": "청구항 1\n배터리 — naïve\n".encode(),
    "markers.txt": (
        b"D8-FILE-END markers.txt\n"
        b"D8-FILE-BEGIN other.txt " + FAKE_DIGEST.encode() + b" 3\n"
        b"D8-INDEX markers.txt " + FAKE_DIGEST.encode() + b" 1\n"
        b"abc\n"
    ),
    "timestamps.txt": (
        b"2026-11-12T10:11:12.1234567Z looks like a log prefix\n2026-01-01T00:00:00Z\n"
    ),
    "with spaces/file name.txt": b"path with spaces\n",
}


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    for relative, data in AWKWARD.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def emitted(source: Path) -> str:
    out = io.BytesIO()
    d8_report.emit(source, out)
    return out.getvalue().decode("utf-8")


def assert_untouched(dest: Path) -> None:
    assert not dest.exists() or not any(dest.rglob("*")), list(dest.rglob("*"))


# -- round trip ------------------------------------------------------------------


def _assert_recovered(dest: Path) -> None:
    for relative, data in AWKWARD.items():
        assert (dest / relative).read_bytes() == data, relative
    assert {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()} == set(AWKWARD)


def test_round_trip_without_prefixes(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "out"
    files = d8_recover.recover(emitted(source), dest)
    assert len(files) == len(AWKWARD)
    _assert_recovered(dest)


@pytest.mark.parametrize(
    ("crlf", "bare_empty"), [(False, False), (False, True), (True, False), (True, True)]
)
def test_round_trip_with_timestamp_prefixes(
    source: Path, tmp_path: Path, crlf: bool, bare_empty: bool
) -> None:
    log = (
        "2026-11-12T10:00:00.0000000Z ##[group]Run python -m evals.d8_report\n"
        + stamp(emitted(source), crlf=False, bare_empty=bare_empty)
        + "\n2026-11-12T10:20:00.0000000Z Post job cleanup.\n"
    )
    if crlf:
        log = log.replace("\n", "\r\n")
    dest = tmp_path / "out"
    d8_recover.recover(log, dest)
    _assert_recovered(dest)


def test_round_trip_with_noise_around_the_blocks(source: Path, tmp_path: Path) -> None:
    log = "step output\n\nanother line\n" + emitted(source) + "post job\n"
    d8_recover.recover(log, tmp_path / "out")
    _assert_recovered(tmp_path / "out")


def test_round_trip_survives_a_byte_order_mark(source: Path, tmp_path: Path) -> None:
    d8_recover.recover("\ufeff" + stamp(emitted(source)), tmp_path / "out")
    _assert_recovered(tmp_path / "out")


def test_marker_lines_inside_content_do_not_end_a_block(tmp_path: Path) -> None:
    """Blocks are read by byte count; searching for END would cut this one short."""
    content = b"first\nD8-FILE-END trap.txt\nsecond\n"
    log = block("trap.txt", content)
    files = d8_recover.parse_log(log)
    assert [(f.path, f.data) for f in files] == [("trap.txt", content)]
    # and the same through a stamped log
    assert d8_recover.parse_log(stamp(log))[0].data == content


def test_a_content_line_that_looks_like_a_timestamp_is_kept(tmp_path: Path) -> None:
    content = b"2026-11-12T10:11:12Z kept\n"
    unprefixed = block("t.txt", content)
    assert d8_recover.parse_log(unprefixed)[0].data == content
    prefixed = stamp(unprefixed)
    assert d8_recover.parse_log(prefixed)[0].data == content


def test_end_to_end_with_the_real_report_tool(tmp_path: Path) -> None:
    """Emit a whole validated run, wrap it like a log, recover, compare bytes."""
    from tests.test_d8_report import make_run, run_tool

    run = make_run(tmp_path)
    assert run_tool(run) == 0
    out = io.BytesIO()
    index = d8_report.emit(run, out)
    log = stamp(out.getvalue().decode("utf-8"))
    dest = tmp_path / "recovered"
    files = d8_recover.recover(log, dest)
    assert {(f.path, f.sha256, len(f.data)) for f in files} == set(index)
    for relative, _, _ in index:
        assert (dest / relative).read_bytes() == (run / relative).read_bytes()


def test_cli_prints_one_line_per_file(
    source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_file = tmp_path / "job.log"
    log_file.write_text(stamp(emitted(source)), encoding="utf-8")
    dest = tmp_path / "out"
    assert d8_recover.main([str(log_file), str(dest)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(AWKWARD)
    assert f"plain.json {len(AWKWARD['plain.json'])} {sha(AWKWARD['plain.json'])}" in lines
    _assert_recovered(dest)


# -- refusals: nothing is written ------------------------------------------------


def test_refuses_a_hash_mismatch_and_writes_nothing(
    source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = emitted(source).replace('{"a": 1}', '{"a": 2}')  # same length, other content
    log_file = tmp_path / "job.log"
    log_file.write_text(log, encoding="utf-8")
    dest = tmp_path / "out"
    assert d8_recover.main([str(log_file), str(dest)]) == 1
    err = capsys.readouterr().err
    assert "sha256 mismatch" in err and "plain.json" in err and "nothing was written" in err
    assert_untouched(dest)


def test_one_bad_block_stops_all_files(tmp_path: Path) -> None:
    log = block("good.txt", b"ok\n") + block("bad.txt", b"abc\n", digest=FAKE_DIGEST)
    dest = tmp_path / "out"
    with pytest.raises(d8_recover.RecoverRefused, match="sha256 mismatch"):
        d8_recover.recover(log, dest)
    assert_untouched(dest)


def test_refuses_a_truncated_block(tmp_path: Path) -> None:
    full = block("a.txt", b"line one\nline two\nline three\n")
    truncated = "\n".join(full.split("\n")[:3])  # BEGIN, two content lines, no more
    dest = tmp_path / "out"
    with pytest.raises(d8_recover.RecoverRefused, match="truncated"):
        d8_recover.recover(truncated, dest)
    assert_untouched(dest)


def test_refuses_a_block_cut_before_its_end_marker(tmp_path: Path) -> None:
    full = block("a.txt", b"abc\n")
    without_end = full[: full.index("D8-FILE-END")]
    with pytest.raises(d8_recover.RecoverRefused, match="unterminated|truncated"):
        d8_recover.parse_log(without_end)


def test_refuses_a_missing_end_marker_followed_by_another_block() -> None:
    first = block("a.txt", b"abc\n").replace("D8-FILE-END a.txt\n", "")
    with pytest.raises(d8_recover.RecoverRefused):
        d8_recover.parse_log(first + block("b.txt", b"xyz\n"))


def test_refuses_a_wrong_byte_count() -> None:
    too_small = block("a.txt", b"abcdef\n", size=3)
    with pytest.raises(d8_recover.RecoverRefused):
        d8_recover.parse_log(too_small)
    too_big = block("a.txt", b"abcdef\n", size=50)
    with pytest.raises(d8_recover.RecoverRefused):
        d8_recover.parse_log(too_big)


def test_refuses_a_stamped_block_that_lost_a_prefix() -> None:
    log = stamp(block("a.txt", b"one\ntwo\n"))
    damaged = log.replace("2026-11-12T10:11:02.1234567Z two", "two")
    assert damaged != log
    with pytest.raises(d8_recover.RecoverRefused, match="lost its timestamp prefix"):
        d8_recover.parse_log(damaged)


@pytest.mark.parametrize(
    "path",
    [
        "../escape.txt",
        "a/../../escape.txt",
        "a/../b.txt",
        "/etc/passwd",
        "C:/windows/x.txt",
        "a\\b.txt",
        "./x.txt",
        "a//b.txt",
        "dir/",
    ],
)
def test_refuses_unsafe_paths(tmp_path: Path, path: str) -> None:
    dest = tmp_path / "out"
    log = block(path, b"payload\n")  # hash and count are correct; only the path is bad
    with pytest.raises(d8_recover.RecoverRefused, match="unsafe path"):
        d8_recover.recover(log, dest)
    assert_untouched(dest)
    assert not (tmp_path / "escape.txt").exists()


def test_refuses_a_path_that_resolves_outside_through_a_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "link").symlink_to(outside)
    with pytest.raises(d8_recover.RecoverRefused, match="outside the destination"):
        d8_recover.recover(block("link/x.txt", b"payload\n"), dest)
    assert not any(outside.iterdir())


def test_refuses_an_existing_file_without_force_and_writes_nothing_else(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "old.txt").write_text("keep me", encoding="utf-8")
    log = block("new.txt", b"new\n") + block("old.txt", b"replacement\n")
    with pytest.raises(d8_recover.RecoverRefused, match="already exists"):
        d8_recover.recover(log, dest)
    assert (dest / "old.txt").read_text(encoding="utf-8") == "keep me"
    assert not (dest / "new.txt").exists()


def test_force_overwrites_existing_files(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "old.txt").write_text("keep me", encoding="utf-8")
    d8_recover.recover(block("old.txt", b"replacement\n"), dest, force=True)
    assert (dest / "old.txt").read_bytes() == b"replacement\n"


def test_cli_existing_file_needs_force(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log_file = tmp_path / "job.log"
    log_file.write_text(block("x.txt", b"data\n"), encoding="utf-8")
    dest = tmp_path / "out"
    assert d8_recover.main([str(log_file), str(dest)]) == 0
    capsys.readouterr()
    assert d8_recover.main([str(log_file), str(dest)]) == 1
    assert "already exists" in capsys.readouterr().err
    assert d8_recover.main([str(log_file), str(dest), "--force"]) == 0


def test_refuses_a_duplicate_path() -> None:
    with pytest.raises(d8_recover.RecoverRefused, match="more than one block"):
        d8_recover.parse_log(block("a.txt", b"1\n") + block("a.txt", b"1\n"))


def test_refuses_a_log_without_blocks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log_file = tmp_path / "job.log"
    log_file.write_text("nothing to see\n", encoding="utf-8")
    assert d8_recover.main([str(log_file), str(tmp_path / "out")]) == 1
    assert "no D8-FILE-BEGIN block" in capsys.readouterr().err


def test_refuses_a_stray_end_marker() -> None:
    with pytest.raises(d8_recover.RecoverRefused, match="outside a block"):
        d8_recover.parse_log(block("a.txt", b"x\n") + "D8-FILE-END a.txt\n")


def test_refuses_an_unreadable_log_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert d8_recover.main([str(tmp_path / "missing.log"), str(tmp_path / "out")]) == 1
    assert "cannot read the log" in capsys.readouterr().err


# -- the index cross-check -------------------------------------------------------


def test_index_must_agree_with_the_blocks() -> None:
    data = b"abc\n"
    good = block("a.txt", data) + f"D8-INDEX a.txt {sha(data)} {len(data)}\n"
    assert d8_recover.parse_log(good)[0].data == data

    wrong_hash = block("a.txt", data) + f"D8-INDEX a.txt {FAKE_DIGEST} {len(data)}\n"
    with pytest.raises(d8_recover.RecoverRefused, match="D8-INDEX disagrees"):
        d8_recover.parse_log(wrong_hash)

    missing_block = block("a.txt", data) + f"D8-INDEX b.txt {sha(data)} {len(data)}\n"
    with pytest.raises(d8_recover.RecoverRefused, match="no verified block"):
        d8_recover.parse_log(missing_block)

    unlisted = (
        block("a.txt", data) + block("b.txt", data) + f"D8-INDEX a.txt {sha(data)} {len(data)}\n"
    )
    with pytest.raises(d8_recover.RecoverRefused, match="not listed in D8-INDEX"):
        d8_recover.parse_log(unlisted)
