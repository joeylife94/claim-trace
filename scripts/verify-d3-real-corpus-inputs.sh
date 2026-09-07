#!/bin/sh
set -eu

MANIFEST="${CLAIMTRACE_D3_MANIFEST:-docs/real-public-corpus/manifest.json}"
CORPUS_DIR="${CLAIMTRACE_D3_CORPUS_DIR:-build/d3-real-corpus/source}"
OUT_DIR="${CLAIMTRACE_D3_OUT:-build/d3-real-corpus/evidence}"

command -v python3 >/dev/null
command -v pdftotext >/dev/null
mkdir -p "$OUT_DIR/text"

set +e
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
display_re = re.compile(r"^10-\d{4}-\d{7}$")
sha256_re = re.compile(r"^[0-9a-f]{64}$")
seen = set()
results = []
failures = []
for item in documents:
    publication = item.get("publication_number", "")
    if not publication_re.match(publication):
        raise SystemExit(f"invalid Korean publication number: {publication!r}")
    if publication in seen:
        raise SystemExit(f"duplicate publication number: {publication}")
    seen.add(publication)

    display_number = item.get("publication_display_number", "")
    if not display_re.match(display_number):
        raise SystemExit(f"{publication}: invalid publication_display_number: {display_number!r}")
    expected_sha256 = item.get("expected_sha256", "")
    if not sha256_re.match(expected_sha256):
        raise SystemExit(f"{publication}: missing or invalid expected_sha256")

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
        failures.append(f"{publication}: local public PDF missing: {pdf_path}")
        results.append({"publication_number": publication, "support_classification": "missing"})
        continue
    data = pdf_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if not data.startswith(b"%PDF-"):
        failures.append(f"{publication}: input is not a PDF")
        results.append({
            "publication_number": publication,
            "sha256": digest,
            "expected_sha256": expected_sha256,
            "bytes": len(data),
            "support_classification": "not_pdf",
        })
        continue
    if digest != expected_sha256:
        failures.append(f"{publication}: SHA-256 mismatch; expected={expected_sha256} actual={digest}")
        results.append({
            "publication_number": publication,
            "sha256": digest,
            "expected_sha256": expected_sha256,
            "bytes": len(data),
            "support_classification": "identity_hash_mismatch",
        })
        continue

    text_path = out_dir / "text" / f"{publication}.txt"
    proc = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(text_path)],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        failures.append(f"{publication}: pdftotext failed: {proc.stderr.strip()}")
        results.append({
            "publication_number": publication,
            "sha256": digest,
            "expected_sha256": expected_sha256,
            "bytes": len(data),
            "support_classification": "pdftotext_failure",
        })
        continue

    text = text_path.read_text(encoding="utf-8", errors="replace")
    identity_present = display_number in text
    if not identity_present:
        failures.append(f"{publication}: extracted text does not contain expected publication identity {display_number}")
    nonspace = sum(not ch.isspace() for ch in text)
    hangul = sum("가" <= ch <= "힣" for ch in text)
    claim_signal = ("청구" in text) or ("Claims" in text) or ("claim" in text.lower())
    supported = nonspace >= 500 and hangul >= 50 and claim_signal and identity_present
    result = {
        "publication_number": publication,
        "publication_display_number": display_number,
        "publication_identity_present": identity_present,
        "application_number": item.get("application_number"),
        "title_ko": item.get("title_ko"),
        "source_page": item["source_page"],
        "acquisition_url": item["acquisition_url"],
        "local_filename": filename,
        "sha256": digest,
        "expected_sha256": expected_sha256,
        "sha256_matches_manifest": digest == expected_sha256,
        "bytes": len(data),
        "extracted_nonspace_chars": nonspace,
        "extracted_hangul_chars": hangul,
        "claim_signal_present": claim_signal,
        "support_classification": "supported_text_pdf" if supported else "unsupported_or_identity_mismatch_pdf",
    }
    results.append(result)
    if nonspace < 500 or hangul < 50 or not claim_signal:
        failures.append(
            f"{publication}: unsupported/non-text input; nonspace={nonspace} hangul={hangul} claim_signal={claim_signal}"
        )

passed = not failures
report = {
    "schema_version": 1,
    "destination": manifest.get("destination"),
    "milestone": manifest.get("milestone"),
    "result": "PASS" if passed else "FAIL",
    "claim_boundary": manifest.get("evidence_boundary"),
    "documents": results,
    "failures": failures,
    "limitations": [
        "Pinned SHA-256 and publication identity bind acquired bytes to this bounded corpus; they do not establish legal or semantic correctness.",
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
    f"**Result:** {'PASS' if passed else 'FAIL'} — bounded public-source inputs are reported without synthetic fallback.",
    "",
    "| Publication | SHA-256 pinned | Identity | Bytes | Non-space chars | Hangul chars | Claim signal | Classification |",
    "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
]
for result in results:
    lines.append(
        f"| {result['publication_number']} | {result.get('sha256_matches_manifest', '-')} | "
        f"{result.get('publication_identity_present', '-')} | {result.get('bytes', '-')} | "
        f"{result.get('extracted_nonspace_chars', '-')} | {result.get('extracted_hangul_chars', '-')} | "
        f"{result.get('claim_signal_present', '-')} | {result['support_classification']} |"
    )
if failures:
    lines += ["", "## Explicit failures", ""] + [f"- {failure}" for failure in failures]
lines += [
    "",
    "## Boundary",
    "",
    "This verifies manifest-pinned source bytes, publication identity, and text extraction only. It does not establish legal correctness, semantic entailment, general retrieval quality, universal Korean patent parsing correctness, or OCR support.",
]
(out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

if failures:
    for failure in failures:
        print(failure, file=sys.stderr)
    raise SystemExit(2)
PY
status=$?
set -e

sha256sum "$OUT_DIR/input-evidence.json" "$OUT_DIR/README.md" > "$OUT_DIR/evidence.sha256"
if [ "$status" -ne 0 ]; then
  printf 'D3 real-corpus input verification failed closed; diagnostics: %s\n' "$OUT_DIR/input-evidence.json" >&2
  exit "$status"
fi
printf 'D3 real-corpus input verification passed: %s\n' "$OUT_DIR/input-evidence.json"
