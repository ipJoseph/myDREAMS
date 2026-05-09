"""Runtime smoke-crawler for the dashboard.

Enumerates every Flask route via app.url_map.iter_rules(). For each GET-able
route, builds a URL, hits it with admin basic auth, and records the HTTP
status. For routes with path parameters, substitutes real PRD IDs (one
collection_id, one contact_id, one listing_id, one share_token).

Catches what static analysis can't:
  * Logic bugs (right syntax, wrong runtime result)
  * Schema drift (column referenced doesn't exist at execution time)
  * Empty-result-set edge cases
  * Template fields that ARE in render_template kwargs but break at render
    (e.g. a dict that lacks an expected key)

Output: docs/audits/route-smoke-crawl.json + console summary.

Usage:
    .venv/bin/python scripts/audit/route_smoke_crawler.py [--target=https://app.wncmountain.homes]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

# Real PRD IDs — pulled from `mcp__dreams-db__run_sql` queries against PRD
# during this audit. Update if the underlying rows are deleted.
SAMPLE_IDS = {
    "collection_id": "16881a20-8a19-4cff-ad15-6c7b30bb0a9e",  # SteveLegg1
    "package_id": "16881a20-8a19-4cff-ad15-6c7b30bb0a9e",
    "share_token": "SSKmtEsimY7oHBtlUUMttg",
    "listing_id": "lst_e4d2a185fb51",  # 1299 Black Forest Drive (Canopy)
    "property_id": "lst_e4d2a185fb51",
    "contact_id": "2e81caf3-59d4-4902-af21-c1ee9ae6f8ee",  # Steve Legg
    "lead_id": "2e81caf3-59d4-4902-af21-c1ee9ae6f8ee",
    "buyer_id": "2e81caf3-59d4-4902-af21-c1ee9ae6f8ee",
    "fub_id": "1",
    "user_id": "1",
    "id": "1",
    "pursuit_id": "16881a20-8a19-4cff-ad15-6c7b30bb0a9e",
    "showing_id": "16881a20-8a19-4cff-ad15-6c7b30bb0a9e",
    "template_id": "16881a20-8a19-4cff-ad15-6c7b30bb0a9e",
    "session_id": "16881a20-8a19-4cff-ad15-6c7b30bb0a9e",
    "report_id": "1",
    "stage": "Lead",
    "source": "navica",
    "filename": "test.jpg",
    "share_id": "SSKmtEsimY7oHBtlUUMttg",
    "token": "SSKmtEsimY7oHBtlUUMttg",
    "slug": "wnc-mountain-homes",
    "fmt": "json",
    "date": "2026-05-08",
    "view_id": "default",
    "name": "test",
    "key": "AGENT_NAME",
    "property_path": "test.jpg",
}

# Routes we know are POST-only or destructive — never crawl from this script
SKIP_ENDPOINTS = {
    # Destructive: would delete real production data
    "delete_collection", "api_delete_collection",
    "delete_pursuit",
    "delete_collection_route",
    # Auth-related: side effects, redirects
    "logout", "login_post",
    # Long-running or fetch-only-after-input
    "buyer_collection_brochure",  # heavy PDF gen — skip in smoke
    "collection_brochure",        # heavy PDF gen
    "collection_pdf",
    "contact_package_pdf",
    "pursuit_brochure",
    "agendas_pdf",
    "fub_sync_endpoint",
    "trigger_sync",
    "run_sync",
}

EXCLUDE_PATH_PREFIXES = (
    "/static/", "/api/public/photos/", "/photos/",
)


def discover_routes():
    """Import the dashboard app and return its url_map rules."""
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "apps" / "property-dashboard"))
    # Load .env so the app boots
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    import importlib.util
    spec = importlib.util.spec_from_file_location("dash_app", str(REPO_ROOT / "apps" / "property-dashboard" / "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


def build_url(rule):
    """Return URL with path params substituted, or None if any are unknown."""
    path = str(rule.rule)
    for arg in rule.arguments:
        v = SAMPLE_IDS.get(arg)
        if v is None:
            return None
        # rule.rule has <type:name> or <name>
        for token in (f"<{arg}>", f"<int:{arg}>", f"<string:{arg}>", f"<path:{arg}>", f"<float:{arg}>"):
            path = path.replace(token, str(v))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=os.getenv("CRAWL_TARGET", "https://app.wncmountain.homes"))
    ap.add_argument("--user", default=os.getenv("CRAWL_USER", "admin"))
    ap.add_argument("--password", default=os.getenv("CRAWL_PASSWORD"))
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    if not args.password:
        # Read from local .env to avoid hardcoding
        for line in (REPO_ROOT / ".env").read_text().splitlines():
            if line.startswith("DASHBOARD_PASSWORD="):
                args.password = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

    app = discover_routes()
    sess = requests.Session()
    sess.auth = (args.user, args.password)

    routes_info = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint in SKIP_ENDPOINTS:
            continue
        if any(rule.rule.startswith(p) for p in EXCLUDE_PATH_PREFIXES):
            continue
        if "GET" not in rule.methods:
            continue
        routes_info.append({
            "endpoint": rule.endpoint,
            "rule": str(rule.rule),
            "arguments": list(rule.arguments),
        })

    findings = []
    skipped = []
    crawled = 0
    fives = 0
    fours = 0
    twos = 0
    threes = 0

    for r in routes_info:
        path = None
        rule = next(rr for rr in app.url_map.iter_rules() if rr.endpoint == r["endpoint"] and str(rr.rule) == r["rule"])
        path = build_url(rule)
        if path is None:
            skipped.append({"endpoint": r["endpoint"], "rule": r["rule"], "reason": "unknown path arg"})
            continue
        url = urljoin(args.target, path)
        t0 = time.time()
        try:
            resp = sess.get(url, timeout=args.timeout, allow_redirects=False)
            elapsed = time.time() - t0
            crawled += 1
            status = resp.status_code
            if status >= 500:
                fives += 1
            elif status >= 400:
                fours += 1
            elif status >= 300:
                threes += 1
            else:
                twos += 1
            entry = {
                "endpoint": r["endpoint"], "rule": r["rule"], "url": path,
                "status": status, "elapsed_ms": round(elapsed * 1000),
            }
            if status >= 500:
                # Try to capture error body excerpt
                entry["body_excerpt"] = resp.text[:300] if resp.text else ""
                findings.append(entry)
            elif status >= 400 and status not in (401, 403, 404):
                findings.append(entry)
        except requests.RequestException as e:
            crawled += 1
            findings.append({
                "endpoint": r["endpoint"], "rule": r["rule"], "url": path,
                "status": None, "error": f"{type(e).__name__}: {e}",
            })
            fives += 1
        if args.limit and crawled >= args.limit:
            break

    out = REPO_ROOT / "docs" / "audits" / "route-smoke-crawl.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "target": args.target,
        "routes_total": len(routes_info),
        "routes_crawled": crawled,
        "routes_skipped": len(skipped),
        "skipped": skipped,
        "summary": {"2xx": twos, "3xx": threes, "4xx": fours, "5xx": fives},
        "findings": findings,
    }, indent=2))

    print(f"Target: {args.target}")
    print(f"Routes total: {len(routes_info)}, crawled: {crawled}, skipped: {len(skipped)}")
    print(f"  2xx: {twos}   3xx: {threes}   4xx: {fours}   5xx: {fives}")
    print(f"\nFindings ({len(findings)}):")
    for f in findings[:30]:
        endpoint = f.get("endpoint", "?")
        status = f.get("status", "ERR")
        rule = f.get("rule", "")
        print(f"  [{status}] {endpoint:<40} {rule}")
    if len(findings) > 30:
        print(f"  ...and {len(findings) - 30} more")
    print(f"\nFull report: {out}")


if __name__ == "__main__":
    main()
