# AI DBA on Bare Metal

Feed it a MySQL slow query log (or a DBCheck collection package), and an open-weight model running on **your own hardware** returns a diagnosis + executable SQL.

## Why "Bare Metal"?

- **Data never leaves your network**: slow logs are full of business SQL. Calling a public cloud API means shipping your schema to someone else's servers. With the model on your own box, logs stay in your datacenter.
- **Predictable cost**: deploy once, diagnose unlimited times, no per-token billing.
- **DBA-grade output**: the prompt follows a senior DBA's diagnostic path — root cause first, then executable SQL, then a risk note. No fluff.

## Quick Start

```bash
# 1. Start vLLM (or any OpenAI-compatible endpoint)
# 2. Run
python aidba.py --slowlog /var/log/mysql/slow.log

# Point at your endpoint and model
python aidba.py --slowlog slow.log \
  --api-base http://YOUR-IP:8100/v1 \
  --model deepseek-v4

# Read from a DBCheck collection package
python aidba.py --dbcheck-report report.json
```

Env vars: `AIDBA_API_BASE`, `AIDBA_MODEL`, `OPENAI_API_KEY` (usually unneeded on-prem).

## Sample Output

```
============================================================
1. Diagnosis
Full table scan on 2.84M rows in orders, no index on created_at,
ORDER BY total triggers filesort.

2. Executable SQL
ALTER TABLE orders ADD INDEX idx_created_at (created_at);

3. Risk Note
Adding an index on a large table locks it; run during off-peak
hours or use pt-online-schema-change.
============================================================
```

## Files

- `aidba.py` — main program (stdlib only, zero dependencies)
- `sample-slow.log` — sample slow log, try `python aidba.py --slowlog sample-slow.log`
