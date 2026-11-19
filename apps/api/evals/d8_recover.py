"""Rebuild the files of a D8 run from a GitHub Actions job log.

    python -m evals.d8_recover <log-file> <dest-dir> [--force]

``evals.d8_report --emit`` prints every file of a run into the job log as

    D8-FILE-BEGIN <relative path> <sha256 hex> <byte count>
    <the file's bytes, exactly>
    <one newline, always added by the writer>
    D8-FILE-END <relative path>

followed by ``D8-INDEX <relative path> <sha256 hex> <byte count>`` lines. This tool
reverses that, and it is built to refuse rather than to guess:

* Nothing is written unless every block verifies (byte count and sha256) and every
  path is safe (relative, no ``..``, nothing that escapes the destination).
* Blocks are read **by byte count**, never by searching for the END marker, so a
  content line that looks like a marker cannot end a block early. After the counted
  bytes the next line must be the one added newline and then exactly the END marker;
  anything else is a truncated or damaged block.
* Existing files are never overwritten unless ``--force`` is given.
* When the log carries ``D8-INDEX`` lines they must agree with the blocks.

Log format handled: the API serves each line with an ISO-8601 timestamp and one
space (``2026-11-12T10:11:12.1234567Z ``); lines may also have no prefix, and the
line endings may be CRLF (treated as LF; the emitter refuses files that contain a
carriage return, so none can be lost). Whether a block's lines carry a prefix is
decided by its BEGIN line: if the BEGIN line has one, exactly one prefix is removed
from every line of the block (so a content line that happens to start with a
timestamp is kept intact); if it has none, nothing is removed inside the block.

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z(?: |$)")
_BEGIN = re.compile(r"^D8-FILE-BEGIN (.+) ([0-9a-f]{64}) (\d+)$")
_INDEX = re.compile(r"^D8-INDEX (.+) ([0-9a-f]{64}) (\d+)$")
_END_PREFIX = "D8-FILE-END "


class RecoverRefused(Exception):
    """The log cannot be turned into a verified set of files; ``reasons`` says why."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True, slots=True)
class RecoveredFile:
    path: str
    data: bytes
    sha256: str


def _strip_prefix(line: str) -> tuple[str, bool]:
    match = _TIMESTAMP.match(line)
    if match:
        return line[match.end() :], True
    return line, False


def _unsafe_path(path: str) -> str | None:
    """Why ``path`` may not be written under the destination, or None if it may."""
    if not path:
        return "empty path"
    if "\x00" in path or "\\" in path:
        return "backslash or NUL in the path"
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return "absolute path"
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "path contains an empty, '.' or '..' component"
    return None


def parse_log(text: str) -> list[RecoveredFile]:
    """Extract and verify every block. Raises ``RecoverRefused`` on any problem."""
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    lines = text.split("\n")
    reasons: list[str] = []
    files: list[RecoveredFile] = []
    index_entries: dict[str, tuple[str, int]] = {}
    seen: set[str] = set()

    position = 0
    while position < len(lines):
        raw = lines[position]
        stripped, prefixed = _strip_prefix(raw)
        begin = _BEGIN.match(stripped)
        if begin is None:
            index = _INDEX.match(stripped)
            if index:
                index_entries[index.group(1)] = (index.group(2), int(index.group(3)))
            elif stripped.startswith(_END_PREFIX):
                reasons.append(f"line {position + 1}: END marker outside a block")
            position += 1
            continue

        path, digest, size = begin.group(1), begin.group(2), int(begin.group(3))
        where = f"{path} (line {position + 1})"
        problem = _unsafe_path(path)
        if problem:
            reasons.append(f"{where}: unsafe path, {problem}")
        if path in seen:
            reasons.append(f"{where}: path appears in more than one block")
        seen.add(path)

        # Count bytes, not markers: take lines until the counted bytes plus the one
        # added newline have been read.
        buffer = bytearray()
        cursor = position + 1
        damage: str | None = None
        while len(buffer) < size + 1:
            if cursor >= len(lines):
                damage = f"block is truncated (needs {size} bytes)"
                break
            line = lines[cursor]
            if prefixed:
                line, had = _strip_prefix(line)
                if not had:
                    damage = f"line {cursor + 1} lost its timestamp prefix"
                    break
            buffer += line.encode("utf-8") + b"\n"
            cursor += 1
        if damage:
            reasons.append(f"{where}: {damage}")
            break

        content, rest = bytes(buffer[:size]), bytes(buffer[size:])
        end_line = lines[cursor] if cursor < len(lines) else None
        end_text = _strip_prefix(end_line)[0] if end_line is not None else None
        if rest != b"\n":
            reasons.append(f"{where}: the counted bytes do not end at a line boundary")
            position = cursor
            continue
        if end_text != f"{_END_PREFIX}{path}":
            reasons.append(f"{where}: no matching END marker after {size} bytes (unterminated)")
            position = cursor
            continue
        actual = hashlib.sha256(content).hexdigest()
        if actual != digest:
            reasons.append(f"{where}: sha256 mismatch (log says {digest}, content is {actual})")
        else:
            files.append(RecoveredFile(path=path, data=content, sha256=digest))
        position = cursor + 1

    if not files and not reasons:
        reasons.append("no D8-FILE-BEGIN block found in the log")

    recovered = {item.path: item for item in files}
    for path, (digest, size) in index_entries.items():
        item = recovered.get(path)
        if item is None:
            reasons.append(f"{path}: listed in D8-INDEX but no verified block was recovered")
        elif (item.sha256, len(item.data)) != (digest, size):
            reasons.append(f"{path}: D8-INDEX disagrees with the recovered block")
    if index_entries:
        for path in recovered:
            if path not in index_entries:
                reasons.append(f"{path}: recovered block is not listed in D8-INDEX")

    if reasons:
        raise RecoverRefused(reasons)
    return files


def recover(log_text: str, dest: Path, *, force: bool = False) -> list[RecoveredFile]:
    """Verify the whole log, then write the files. Writes nothing if anything fails."""
    files = parse_log(log_text)
    destination = dest.resolve()
    reasons: list[str] = []
    targets: list[tuple[Path, RecoveredFile]] = []
    for item in files:
        target = (destination / item.path).resolve()
        if destination not in target.parents:
            reasons.append(f"{item.path}: resolves outside the destination")
        elif target.exists() and not force:
            reasons.append(f"{item.path}: already exists (use --force to overwrite)")
        elif target.is_dir():
            reasons.append(f"{item.path}: is an existing directory")
        targets.append((target, item))
    if reasons:
        raise RecoverRefused(reasons)
    for target, item in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.data)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.d8_recover",
        description=(
            "Rebuild the files that `evals.d8_report --emit` printed into a GitHub Actions "
            "job log, verifying byte counts and sha256. Writes nothing unless every block "
            "verifies."
        ),
    )
    parser.add_argument("log_file", type=Path, help="the job log, with or without timestamps")
    parser.add_argument("dest_dir", type=Path, help="directory to recreate the files under")
    parser.add_argument(
        "--force", action="store_true", help="overwrite files that already exist in dest_dir"
    )
    arguments = parser.parse_args(argv)

    try:
        text = arguments.log_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"D8 RECOVER REFUSED: cannot read the log ({error})", file=sys.stderr)
        return 1
    try:
        files = recover(text, arguments.dest_dir, force=arguments.force)
    except RecoverRefused as refusal:
        for reason in refusal.reasons:
            print(f"D8 RECOVER REFUSED: {reason}", file=sys.stderr)
        print("D8 RECOVER REFUSED: nothing was written.", file=sys.stderr)
        return 1
    for item in files:
        print(f"{item.path} {len(item.data)} {item.sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
