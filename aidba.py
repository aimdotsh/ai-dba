#!/usr/bin/env python3
"""
AI DBA - AI DBA on Bare Metal
Feed it a MySQL slow query log, get diagnosis + executable SQL
from an open-weight model running on YOUR hardware.

Usage:
    python aidba.py --slowlog slow.log
    python aidba.py --slowlog slow.log --api-base http://9.7.130.151:8100/v1
    python aidba.py --dbcheck-report report.json

Data never leaves your network: the model runs on your own iron.
"""
import argparse
import json
import os
import re
import sys
import urllib.request


SYSTEM_PROMPT = """You are a senior MySQL DBA. The user gives you
MySQL slow log excerpts. Output:
1. Diagnosis (1-3 sentences, state the root cause directly)
2. Executable SQL (fix the index / rewrite the query / tune a
   parameter — pick one, give the exact statement)
3. Risk note (one sentence)

Answer in English, wrap SQL in code blocks. No fluff."""


def parse_slowlog(path, limit=5):
    """Extract the slowest queries from a MySQL slow log."""
    with open(path, errors="ignore") as f:
        content = f.read()
    # Split on "# Time:" markers
    blocks = re.split(r"# Time:", content)
    queries = []
    for b in blocks[1:]:
        qt = re.search(r"# Query_time:\s*([\d.]+)", b)
        sql_m = re.search(
            r"SET timestamp=\d+;\n(.+?);?\s*(?=# Time:|$)", b, re.S
        )
        if qt and sql_m:
            sql = sql_m.group(1).strip()
            # Skip admin statements
            if re.match(r"(?i)^(use |set |select \* from information_schema)",
                        sql):
                continue
            queries.append((float(qt.group(1)), sql))
    queries.sort(reverse=True)
    return queries[:limit]


def parse_dbcheck_report(path, limit=5):
    """Extract slow queries / alerts from a DBCheck collection JSON."""
    with open(path) as f:
        data = json.load(f)
    items = []
    # Tolerate several field namings
    for key in ("slow_queries", "slowQueries", "top_slow_sql"):
        if key in data:
            for q in data[key][:limit]:
                if isinstance(q, dict):
                    items.append((
                        float(q.get("query_time", q.get("Query_time", 0))),
                        q.get("sql", q.get("SQL", "")),
                    ))
                else:
                    items.append((0, str(q)))
            break
    return items


def call_llm(api_base, model, slow_queries):
    """Call an OpenAI-compatible endpoint (vLLM)."""
    prompt = "Top slow SQL from slow log:\n\n"
    for i, (qt, sql) in enumerate(slow_queries, 1):
        prompt += f"--- SQL #{i} (Query_time: {qt}s) ---\n{sql[:2000]}\n\n"

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1500,
    }).encode()

    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    # On-prem models usually need no key; set OPENAI_API_KEY if yours does
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.load(resp)
    return result["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser(description="AI DBA on Bare Metal")
    ap.add_argument("--slowlog", help="Path to MySQL slow query log")
    ap.add_argument("--dbcheck-report",
                    help="Path to DBCheck collection package JSON")
    ap.add_argument("--api-base", default=os.environ.get(
        "AIDBA_API_BASE", "http://9.7.130.151:8100/v1"),
        help="vLLM OpenAI-compatible endpoint")
    ap.add_argument("--model", default=os.environ.get(
        "AIDBA_MODEL", "deepseek-v4"),
        help="Model name")
    ap.add_argument("--limit", type=int, default=3,
                    help="How many of the slowest SQL to analyze")
    args = ap.parse_args()

    if args.slowlog:
        queries = parse_slowlog(args.slowlog, args.limit)
    elif args.dbcheck_report:
        queries = parse_dbcheck_report(args.dbcheck_report, args.limit)
    else:
        ap.error("must specify --slowlog or --dbcheck-report")

    if not queries:
        print("No slow queries parsed, check the file format.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(queries)} slow queries, sending to model...\n")
    print("=" * 60)
    result = call_llm(args.api_base, args.model, queries)
    print(result)
    print("=" * 60)
    print("\n[AI DBA] Diagnosis complete. Data never left your network.")


if __name__ == "__main__":
    main()
