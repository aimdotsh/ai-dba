#!/usr/bin/env python3
"""
AI DBA - 铁皮上的 AI DBA
把 MySQL 慢日志丢进去，open-weight 模型输出诊断结论 + 可执行 SQL。

用法:
    python aidba.py --slowlog slow.log
    python aidba.py --slowlog slow.log --api-base http://9.7.130.151:8100/v1
    python aidba.py --dbcheck-report report.json

数据不出内网：模型跑在你自己的铁皮上。
"""
import argparse
import json
import os
import re
import sys
import urllib.request


SYSTEM_PROMPT = """你是资深 MySQL DBA。用户给你 MySQL 慢日志片段，
请输出:
1. 诊断结论（1-3 句话，直说问题根因）
2. 可执行的 SQL（修复索引/改写查询/调整参数，三选一，给出具体语句）
3. 风险提示（一句话）

用中文回答，SQL 用代码块。不要废话。"""


def parse_slowlog(path, limit=5):
    """提取慢日志里最慢的几条查询。"""
    with open(path, errors="ignore") as f:
        content = f.read()
    # 按 # Time: 切分
    blocks = re.split(r"# Time:", content)
    queries = []
    for b in blocks[1:]:
        qt = re.search(r"# Query_time:\s*([\d.]+)", b)
        sql_m = re.search(
            r"SET timestamp=\d+;\n(.+?);?\s*(?=# Time:|$)", b, re.S
        )
        if qt and sql_m:
            sql = sql_m.group(1).strip()
            # 跳过管理语句
            if re.match(r"(?i)^(use |set |select \* from information_schema)",
                        sql):
                continue
            queries.append((float(qt.group(1)), sql))
    queries.sort(reverse=True)
    return queries[:limit]


def parse_dbcheck_report(path, limit=5):
    """从 DBCheck 采集包 JSON 里提取慢查询/告警。"""
    with open(path) as f:
        data = json.load(f)
    items = []
    # 兼容多种字段名
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
    """调 OpenAI 兼容接口（vLLM）。"""
    prompt = "慢日志 Top SQL:\n\n"
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
    # 内网模型一般不需要 key；如需，设 OPENAI_API_KEY 环境变量
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.load(resp)
    return result["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser(description="铁皮上的 AI DBA")
    ap.add_argument("--slowlog", help="MySQL 慢日志文件路径")
    ap.add_argument("--dbcheck-report", help="DBCheck 采集包 JSON 路径")
    ap.add_argument("--api-base", default=os.environ.get(
        "AIDBA_API_BASE", "http://9.7.130.151:8100/v1"),
        help="vLLM OpenAI 兼容接口地址")
    ap.add_argument("--model", default=os.environ.get(
        "AIDBA_MODEL", "deepseek-v4"),
        help="模型名")
    ap.add_argument("--limit", type=int, default=3,
                    help="分析几条最慢的 SQL")
    args = ap.parse_args()

    if args.slowlog:
        queries = parse_slowlog(args.slowlog, args.limit)
    elif args.dbcheck_report:
        queries = parse_dbcheck_report(args.dbcheck_report, args.limit)
    else:
        ap.error("必须指定 --slowlog 或 --dbcheck-report")

    if not queries:
        print("没解析到慢查询，检查文件格式。", file=sys.stderr)
        sys.exit(1)

    print(f"解析到 {len(queries)} 条慢查询，送模型诊断...\n")
    print("=" * 60)
    result = call_llm(args.api_base, args.model, queries)
    print(result)
    print("=" * 60)
    print("\n[AI DBA] 诊断完成。数据未离开内网。")


if __name__ == "__main__":
    main()
