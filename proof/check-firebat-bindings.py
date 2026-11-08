#!/usr/bin/env python3
"""Check the Firebat Proof host-publication contract on rendered Compose JSON.

Input is the output of `docker compose ... config --format json` (file path, or
`-` for stdin). Exit codes: 0 all checks pass, 1 contract violated, 2 usage or
JSON error.
"""
import argparse
import json
import sys

EXPECTED_TARGETS = {"postgres": 5432, "api": 8000, "web": 3000, "ollama": 11434}
LOOPBACK = "127.0.0.1"
BROWSER_HOSTS = ("127.0.0.1", "localhost")

failures = 0


def ok(msg):
    print("[PASS] " + msg)


def fail(msg):
    global failures
    failures += 1
    print("[FAIL] " + msg)


def load(path):
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print("error: cannot read JSON from %s: %s" % (path, exc), file=sys.stderr)
        sys.exit(2)


def ports_of(svc):
    return svc.get("ports") or []


def published_of(services, name):
    ports = ports_of(services.get(name, {}))
    if len(ports) == 1:
        return str(ports[0].get("published", ""))
    return None


def check_presence(services):
    for name in EXPECTED_TARGETS:
        if name in services:
            ok("service %s present" % name)
        else:
            fail("service %s missing from rendered config" % name)


def check_host_ip(services):
    bad = 0
    for name, svc in sorted(services.items()):
        for p in ports_of(svc):
            if p.get("host_ip") != LOOPBACK:
                bad += 1
                fail("%s publishes host_ip=%r published=%r target=%r (must be %s)"
                     % (name, p.get("host_ip"), p.get("published"), p.get("target"), LOOPBACK))
    if not bad:
        ok("every published port is bound to %s" % LOOPBACK)


def check_network_mode(services):
    # A host-network container listens on host interfaces directly, bypassing
    # every port publication rule above.
    bad = [name for name, svc in sorted(services.items())
           if str(svc.get("network_mode", "")).startswith("host")]
    for name in bad:
        fail("%s uses network_mode=%r, which bypasses port publication" % (name, services[name]["network_mode"]))
    if not bad:
        ok("no service uses host networking")


def check_shape(services):
    for name, target in EXPECTED_TARGETS.items():
        if name not in services:
            continue
        ports = ports_of(services[name])
        targets = [int(p.get("target", 0)) for p in ports]
        if len(ports) == 1 and targets == [target]:
            ok("%s has exactly one port entry (target %d)" % (name, target))
        else:
            fail("%s must have exactly one port entry with target %d, got targets %s"
                 % (name, target, targets))


def check_urls(services):
    web_pub = published_of(services, "web")
    api_pub = published_of(services, "api")
    cors = (services.get("api", {}).get("environment") or {}).get("CORS_ALLOW_ORIGINS")
    base = (services.get("web", {}).get("environment") or {}).get("NEXT_PUBLIC_API_BASE_URL")

    if web_pub is None or cors is None:
        fail("cannot verify CORS_ALLOW_ORIGINS (web published port or value unavailable)")
    else:
        allowed = {"http://%s:%s" % (h, web_pub) for h in BROWSER_HOSTS}
        origins = [o.strip() for o in str(cors).split(",") if o.strip()]
        bad = [o for o in origins if o not in allowed]
        if origins and not bad:
            ok("CORS_ALLOW_ORIGINS only allows loopback web origin(s): %s" % ", ".join(origins))
        else:
            fail("CORS_ALLOW_ORIGINS=%r must contain only %s" % (cors, " or ".join(sorted(allowed))))

    if api_pub is None or base is None:
        fail("cannot verify NEXT_PUBLIC_API_BASE_URL (api published port or value unavailable)")
    else:
        allowed = {"http://%s:%s" % (h, api_pub) for h in BROWSER_HOSTS}
        if str(base).rstrip("/") in allowed and str(base).count("/") <= 3:
            ok("NEXT_PUBLIC_API_BASE_URL=%s matches the published API port" % base)
        else:
            fail("NEXT_PUBLIC_API_BASE_URL=%r must be exactly %s (a non-loopback browser URL "
                 "needs a separately reviewed route)" % (base, " or ".join(sorted(allowed))))


def check_baseline(cand, base):
    diffs = 0
    if cand.get("name") != base.get("name"):
        diffs += 1
        fail("project name differs: %r vs baseline %r" % (cand.get("name"), base.get("name")))
    cs, bs = cand.get("services", {}), base.get("services", {})
    for name in sorted(set(cs) | set(bs)):
        if name not in cs or name not in bs:
            diffs += 1
            fail("service %s exists only in %s" % (name, "candidate" if name in cs else "baseline"))
            continue
        c = {k: v for k, v in cs[name].items() if k != "ports"}
        b = {k: v for k, v in bs[name].items() if k != "ports"}
        for key in sorted(set(c) | set(b)):
            if c.get(key) != b.get(key):
                diffs += 1
                fail("service %s key %s differs from baseline" % (name, key))
    for key in ("volumes", "networks"):
        if cand.get(key) != base.get(key):
            diffs += 1
            fail("top-level %s differ from baseline" % key)
    if not diffs:
        ok("overlay changes host port publication only (matches baseline apart from ports)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("candidate", help="rendered config JSON path, or - for stdin")
    ap.add_argument("--baseline", help="rendered JSON of the base compose without the overlay")
    args = ap.parse_args()

    cand = load(args.candidate)
    base = load(args.baseline) if args.baseline else None
    if not isinstance(cand, dict) or not isinstance(cand.get("services"), dict):
        print("error: candidate JSON has no 'services' object", file=sys.stderr)
        sys.exit(2)
    services = cand["services"]

    check_presence(services)
    check_host_ip(services)
    check_network_mode(services)
    check_shape(services)
    check_urls(services)
    if base is not None:
        check_baseline(cand, base)

    if failures:
        print("[FAIL] Firebat binding contract (%d failures)" % failures)
        sys.exit(1)
    print("[PASS] Firebat binding contract")


if __name__ == "__main__":
    main()
