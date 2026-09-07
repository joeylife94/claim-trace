#!/bin/sh
set -eu

MANIFEST="${CLAIMTRACE_D3_MANIFEST:-docs/real-public-corpus/manifest.json}"
CORPUS_DIR="${CLAIMTRACE_D3_CORPUS_DIR:-build/d3-real-corpus/source}"
OUT_DIR="${CLAIMTRACE_D3_OUT:-build/d3-real-corpus/evidence}"

command -v python3 >/dev/null
command -v pdftotext >/dev/null
mkdir -p "$OUT_DIR/text"

python3 - "$MANIFEST" "$CORPUS_DIR" "$OUT_DIR" <<'PY'
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
corpus_dir = Path(sys.argv[2])
out_dir = Path(sys.argv[3])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
documents = manifest.get("documents")
if not isinstance(documents, list) or not (2 <= len(documents) <= 5):
    raise SystemExit("D3 corpus must contain 2-5 bounded documents")

publication_re = re.compile(r"^KR\d{8,12}[A-Z]\d?$")
seen = set()
results = []
for item in documents:
    publication = item.get("publication_number", "")
    if not publication_re.match(publication):
        raise SystemExit(f"invalid Korean publication number: {publication!r}")
    if publication in seen:
        raise SystemExit(f"duplicate publication number: {publication}")
    seen.add(publication)

    for key in ("canonical_lookup", "source_page", "acquisition_url"):
        value = item.get(key, "")
        if not isinstance(value, str) or not value.startswith("https://"):
            raise SystemExit(f"{publication}: missing HTTPS {key}")
    if item.get("redistribution_status") != "not_asserted_do_not_commit_pdf":
        raise SystemExit(f"{publication}: redistribution boundary must remain explicit")

    filename = item.get("local_filename", "")
    if filename != f"{publication}.pdf":
        raise SystemExit(f"{publication}: local filename must be canonical")
    pdf_path = corpus_dir / filename
    if not pdf_path.is_file():
        raise SystemExit(f"{publication}: local public PDF missing: {pdf_path}")
    data = pdf_path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise SystemExit(f"{publication}: input is not a PDF")
    digest = hashlib.sha256(data).hexdigest()

    text_path = out_dir / "text" / f"{publication}.txt"
    proc = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(text_path)],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"{publication}: pdftotext failed: {proc.stderr.strip()}")
    text = text_path.read_text(encoding="utf-8", errors="replace")
    nonspace = sum(not ch.isspace() for ch in text)
    hangul = sum("가" <= ch <= "힣" for ch in text)
    claim_signal = ("청구" in text) or ("Claims" in text) or ("claim" in text.lower())
    supported = nonspace >= 500 and hangul >= 50 and claim_signal
    result = {
        "publication_number": publication,
        "application_number": item.get("application_number"),
        "title_ko": item.get("title_ko"),
        "source_page": item["source_page"],
        "acquisition_url": item["acquisition_url"],
        "local_filename": filename,
        "sha256": digest,
        "bytes": len(data),
        "extracted_nonspace_chars": nonspace,
        "extracted_hangul_chars": hangul,
        "claim_signal_present": claim_signal,
        "support_classification": "supported_text_pdf" if supported else "unsupported_or_nontext_pdf",
    }
    results.append(result)
    if not supported:
        raise SystemExit(
            f"{publication}: unsupported/non-text input; nonspace={nonspace} hangul={hangul} claim_signal={claim_signal}"
        )

report = {
    "schema_version": 1,
    "destination": manifest.get("destination"),
    "milestone": manifest.get("milestone"),
    "result": "PASS",
    "claim_boundary": manifest.get("evidence_boundary"),
    "documents": results,
    "limitations": [
        "Input support classification proves extractable text plumbing only, not parser, retrieval, semantic, or legal correctness.",
        "PDF redistribution rights are not asserted; source PDFs are locally acquired and are not repository artifacts.",
        "OCR/scanned/image-only recovery is not part of D3-01.",
    ],
}
(out_dir / "input-evidence.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

lines = [
    "# D3-01 Real Public Corpus Input Evidence",
    "",
    "**Result:** PASS — bounded inputs are public-source-referenced, hashed, and text-extractable.",
    "",
    "| Publication | SHA-256 | Bytes | Non-space chars | Hangul chars | Classification |",
    "| --- | --- | ---: | ---: | ---: | --- |",
]
for result in results:
    lines.append(
        f"| {result['publication_number']} | `{result['sha256']}` | {result['bytes']} | "
        f"{result['extracted_nonspace_chars']} | {result['extracted_hangul_chars']} | "
        f"{result['support_classification']} |"
    )
lines += [
    "",
    "## Boundary",
    "",
    "This verifies source-linked local PDF bytes and text extraction only. It does not establish legal correctness, semantic entailment, general retrieval quality, universal Korean patent parsing correctness, or OCR support.",
]
(out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

sha256sum "$OUT_DIR/input-evidence.json" "$OUT_DIR/README.md" > "$OUT_DIR/evidence.sha256"
printf 'D3 real-corpus input verification passed: %s\n' "$OUT_DIR/input-evidence.json"
