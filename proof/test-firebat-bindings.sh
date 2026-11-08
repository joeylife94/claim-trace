#!/usr/bin/env bash
# Offline tests for the Firebat Proof host-publication contract.
# Run from the repository root. Needs only the `docker compose` CLI (config
# rendering) and python3; no Docker daemon is contacted.
set -uo pipefail

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

pass=0
fail=0
ok()  { echo "[PASS] $1"; pass=$((pass + 1)); }
bad() { echo "[FAIL] $1"; fail=$((fail + 1)); }

# Run a command with the Firebat-relevant variables removed from its environment.
clean() {
  env -u POSTGRES_PORT -u API_PORT -u WEB_PORT -u OLLAMA_PORT \
      -u CORS_ALLOW_ORIGINS -u NEXT_PUBLIC_API_BASE_URL "$@"
}

# Explicit Firebat env, so rendering never depends on a developer's .env.
firebat_env() {
  env POSTGRES_PORT=15432 OLLAMA_PORT=11435 API_PORT=18000 WEB_PORT=13000 \
      CORS_ALLOW_ORIGINS=http://127.0.0.1:13000 \
      NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:18000 "$@"
}

expect_zero() {   # name, command...
  local name="$1"; shift
  if "$@" >"$scratch/out.log" 2>&1; then ok "$name"; else bad "$name"; sed 's/^/    /' "$scratch/out.log"; fi
}
# A negative case passes only if the command fails AND prints the expected
# failure, so a rendering error or usage error cannot masquerade as rejection.
expect_failure() {   # name, expected-output regex, command...
  local name="$1" pattern="$2"; shift 2
  if "$@" >"$scratch/out.log" 2>&1; then
    bad "$name (unexpectedly passed)"; sed 's/^/    /' "$scratch/out.log"
  elif grep -Eq -- "$pattern" "$scratch/out.log"; then
    ok "$name"
  else
    bad "$name (failed without the expected message: $pattern)"; sed 's/^/    /' "$scratch/out.log"
  fi
}

# Render a config to a file; a rendering failure is a test failure, never a
# silent empty input for a negative case.
render() {   # output-file, compose args...
  local out="$1"; shift
  if ! firebat_env docker compose "$@" config --format json >"$out" 2>"$scratch/render.err"; then
    bad "rendering failed: docker compose $*"; sed 's/^/    /' "$scratch/render.err"
  fi
}

# `config --hash` output must be "<service> <64 hex>"; anything else is empty.
service_hash() {   # service, env/compose command prefix...
  local svc="$1"; shift
  "$@" config --hash "$svc" 2>/dev/null | grep -E "^${svc} [0-9a-f]{64}$" || true
}

# P1: the real start script's --check passes with default settings.
expect_zero "P1 firebat-start.sh --check passes with defaults" \
  clean bash proof/firebat-start.sh --check

# P2: the local-dev default is unchanged (wildcard publication, project
# "claimtrace"). This asserts nothing changed for dev, not that wildcard is
# desirable.
clean docker compose --env-file .env.example --profile llm config --format json >"$scratch/dev.json" 2>"$scratch/dev.err"
if python3 - "$scratch/dev.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["name"] == "claimtrace", d["name"]
want = {"postgres": 5432, "api": 8000, "web": 3000, "ollama": 11434}
for svc, port in want.items():
    ports = d["services"][svc]["ports"]
    assert len(ports) == 1, (svc, ports)
    p = ports[0]
    assert int(p["published"]) == port and p["target"] == port, (svc, p)
    assert "host_ip" not in p or not p["host_ip"], (svc, p)
PY
then ok "P2 dev defaults preserved (claimtrace, default ports, no host_ip)"; else bad "P2 dev defaults changed"; cat "$scratch/dev.err"; fi

# P3: postgres/ollama definitions are identical to the deployed PR #72 shape.
candidate_cmd=(firebat_env docker compose -p claimtrace-proof -f docker-compose.yml -f proof/compose.firebat.yml --profile llm)
pr72_cmd=(firebat_env POSTGRES_PORT=127.0.0.1:15432 OLLAMA_PORT=127.0.0.1:11435 docker compose -p claimtrace-proof -f docker-compose.yml --profile llm)
cand_pg=$(service_hash postgres "${candidate_cmd[@]}")
cand_ol=$(service_hash ollama "${candidate_cmd[@]}")
old_pg=$(service_hash postgres "${pr72_cmd[@]}")
old_ol=$(service_hash ollama "${pr72_cmd[@]}")
if [[ -n "$cand_pg" && "$cand_pg" == "$old_pg" && -n "$cand_ol" && "$cand_ol" == "$old_ol" ]]; then
  ok "P3 postgres/ollama config hashes match the PR #72 shape"
else
  bad "P3 config hashes differ (postgres: '$cand_pg' vs '$old_pg'; ollama: '$cand_ol' vs '$old_ol')"
fi

checker() { python3 proof/check-firebat-bindings.py "$@"; }
# Wildcard publication renders as a port entry without host_ip.
wildcard_msg='publishes host_ip=None'

# N1: the base compose with no overlay (wildcard) must be rejected.
render "$scratch/n1.json" -p claimtrace-proof -f docker-compose.yml --profile llm
expect_failure "N1 base compose without overlay is rejected" "$wildcard_msg" checker "$scratch/n1.json"

# N2: overlay without !override merges lists and keeps the wildcard entry.
sed 's/ports: !override/ports:/' proof/compose.firebat.yml >"$scratch/merge.yml"
if grep -q 'ports: !override' "$scratch/merge.yml"; then bad "N2 sed failed to strip !override"; fi
render "$scratch/n2.json" -p claimtrace-proof -f docker-compose.yml -f "$scratch/merge.yml" --profile llm
expect_failure "N2 overlay without !override (merged wildcard) is rejected" "$wildcard_msg" checker "$scratch/n2.json"

# N7: host networking bypasses publication entirely and must be rejected even
# when every ports entry is loopback.
printf 'services:\n  api:\n    network_mode: host\n' >"$scratch/hostnet.yml"
render "$scratch/n7.json" -p claimtrace-proof -f docker-compose.yml -f proof/compose.firebat.yml -f "$scratch/hostnet.yml" --profile llm
expect_failure "N7 host network mode rejected" 'api uses network_mode=' checker "$scratch/n7.json"

# N3-N6, N8: the start script rejects bad input before touching containers.
port_msg='must be a port number'
expect_failure "N3 legacy POSTGRES_PORT=127.0.0.1:15432 rejected" "POSTGRES_PORT $port_msg" \
  clean env POSTGRES_PORT=127.0.0.1:15432 bash proof/firebat-start.sh --check
expect_failure "N4 WEB_PORT=abc rejected" "WEB_PORT $port_msg" \
  clean env WEB_PORT=abc bash proof/firebat-start.sh --check
expect_failure "N5 non-loopback CORS origin rejected" '\[FAIL\] CORS_ALLOW_ORIGINS=' \
  clean env CORS_ALLOW_ORIGINS=http://192.168.0.10:13000 bash proof/firebat-start.sh --check
expect_failure "N6 NEXT_PUBLIC_API_BASE_URL port mismatch rejected" '\[FAIL\] NEXT_PUBLIC_API_BASE_URL=' \
  clean env NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 bash proof/firebat-start.sh --check
# 2^64 + 1 would wrap to 1 in bash arithmetic without the digit-count bound.
expect_failure "N8 oversized API_PORT rejected" "API_PORT $port_msg" \
  clean env API_PORT=18446744073709551617 bash proof/firebat-start.sh --check

echo "$pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
