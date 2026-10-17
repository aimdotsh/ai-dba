# 铁皮上的 AI DBA

把 MySQL 慢日志（或 DBCheck 采集包）丢进去，跑在**你自己铁皮上**的 open-weight 模型输出诊断结论 + 可执行 SQL。

## 为什么是"铁皮上"？

- **数据不出内网**：慢日志里全是业务 SQL，调公有云 API 等于把库结构裸奔。模型跑在自己的机器上，日志不出机房。
- **成本可控**：一次部署，无限次诊断，不按 token 挨刀。
- **DBA 味**：prompt 按资深 DBA 的诊断路径写——先定根因，再给可执行 SQL，最后风险提示。不废话。

## 快速开始

```bash
# 1. 起一个 vLLM（或任何 OpenAI 兼容接口）
# 2. 跑
python aidba.py --slowlog /var/log/mysql/slow.log

# 指定接口和模型
python aidba.py --slowlog slow.log \
  --api-base http://你的IP:8100/v1 \
  --model deepseek-v4

# 从 DBCheck 采集包读
python aidba.py --dbcheck-report report.json
```

环境变量：`AIDBA_API_BASE`、`AIDBA_MODEL`、`OPENAI_API_KEY`（内网一般不需要）。

## 输出示例

```
============================================================
1. 诊断结论
orders 表 284 万行全表扫描，created_at 上没有索引，
ORDER BY total 触发 filesort。

2. 可执行 SQL
ALTER TABLE orders ADD INDEX idx_created_at (created_at);

3. 风险提示
大表加索引会锁表，业务低峰期执行，或用 pt-online-schema-change。
============================================================
```

## 文件

- `aidba.py` — 主程序（零依赖，只用标准库）
- `sample-slow.log` — 示例慢日志，跑 `python aidba.py --slowlog sample-slow.log` 试试
