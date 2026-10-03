# HacKU · Contribution Graph

一个用于记录团队任务贡献、同伴核验与协作关系的本地 Web 应用。项目按 `CORE`（核心）、`SUPPORT`（支持）、`REVIEW`（审查）和 `COORDINATION`（协调）四类贡献计分；待核验或争议中的贡献暂不计分。

## 功能

- **贡献录入**：在看板中创建或切换项目、添加成员和任务、提交四类贡献；新贡献以「待验证」状态出现，提交后得分为 0。
- **贡献审核**：独立的审核页面可为贡献添加证据、同伴确认或调整分值、提出及解决争议，并保留完整的核验与争议记录；调整前先预览分数，确认分数实际变化后才提交。
- **项目看板**：查看团队总分、成员得分及占比、任务价值和贡献明细。
- **协作关系图**：展示「成员 → 贡献 → 任务」关系，以虚线标出受帮助成员，并与明细、成员和任务筛选联动；支持按类型、状态、得分和成员排序。
- **中英双语**：页头「设置」可在中文与 English 之间切换，选择保存在当前浏览器。
- **统一数据源**：看板、审核页面与命令行共用本地 SQLite 数据库，默认服务地址为 `http://127.0.0.1:8000`。

## 快速开始

需要 Python 3。克隆仓库后，在项目目录中执行：

```sh
cd 'Contribution Graph'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python import_json.py data.json data.sqlite3
.venv/bin/python dashboard_server.py
```

启动后：

- [项目看板](http://127.0.0.1:8000) — 总览、录入、关系图与贡献明细。
- [贡献审核](http://127.0.0.1:8000/review.html) — 证据、同伴验证与争议处理。
- [API 文档](http://127.0.0.1:8000/docs) — 交互式接口说明。

`import_json.py` 仅用于首次初始化，已有 `data.sqlite3` 时无需再次导入。SQLite 文件不进入 Git；仓库中的 `data.json` 是可移植的数据快照。

## 项目结构

| 路径 | 作用 |
|---|---|
| `Contribution Graph/contribution_engine.py` | 数据模型、校验和评分规则 |
| `Contribution Graph/contribution_store.py` | SQLite 读写、业务流程与命令行 |
| `Contribution Graph/dashboard_server.py` | FastAPI 接口与静态页面服务 |
| `Contribution Graph/dashboard/` | 看板（`index.html`、`app.js`、`style.css`）与审核页面（`review.html`、`review.js`、`review.css`） |
| `Contribution Graph/schema.sql` | 数据库表、外键和索引 |
| `Contribution Graph/data.json` | 合并后的项目数据快照 |
| `Contribution Graph/import_json.py`、`export_json.py`、`merge_sqlite.py` | 快照导入、导出与历史数据库合并工具 |

目前快照含 1 个项目、4 名成员、4 项任务、6 条贡献，以及对应的核验和争议记录。运行时以 `data.sqlite3` 为准；更改数据后，运行 `python3 export_json.py` 更新快照。命令行用法、API 路径和完整流程见 [详细文档](Contribution%20Graph/README.md)，审核页面的实现与验收步骤见 [B-实现说明.md](B-实现说明.md)。

## 测试与开发

在 `Contribution Graph/` 中运行：

```sh
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
.venv/bin/python demo_workflow.py
```

前者运行 38 项自动化测试，覆盖评分引擎、SQLite 持久化、数据合并与导入、Dashboard 与审核 API；后者在临时数据库中验证完整贡献流程，不修改网站数据。贡献规范见 [AGENTS.md](AGENTS.md)，历次变更见 [CHANGELOG.md](CHANGELOG.md)。
