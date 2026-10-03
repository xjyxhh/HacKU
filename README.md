# HacKU · Contribution Graph

一个用于记录团队任务贡献、同伴核验与协作关系的本地 Web 应用。项目按 `CORE`（核心）、`SUPPORT`（支持）、`REVIEW`（审查）和 `COORDINATION`（协调）四类贡献计分；待核验或争议中的贡献暂不计分。

## 功能

- **贡献流程**：提交贡献、添加证据、同伴确认或调整、提出及解决争议；保留核验与争议记录。
- **项目看板**：查看团队总分、成员得分及占比、任务价值和贡献明细。
- **协作关系图**：展示成员之间的帮助关系，并与明细、成员和任务筛选联动；支持按类型、状态、得分和成员排序。
- **统一数据源**：网站与命令行共用本地 SQLite 数据库，默认服务地址为 `http://127.0.0.1:8000`。

## 快速开始

需要 Python 3。克隆仓库后，在项目目录中执行：

```sh
cd 'Contribution Graph'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python import_json.py data.json data.sqlite3
.venv/bin/python dashboard_server.py
```

打开 [项目看板](http://127.0.0.1:8000)；交互式 API 文档位于 [API 文档](http://127.0.0.1:8000/docs)。`import_json.py` 仅用于首次初始化，已有 `data.sqlite3` 时无需再次导入。SQLite 文件不进入 Git；仓库中的 `data.json` 是可移植的数据快照。

## 项目结构

| 路径 | 作用 |
|---|---|
| `Contribution Graph/contribution_engine.py` | 数据模型、校验和评分规则 |
| `Contribution Graph/contribution_store.py` | SQLite 读写、业务流程与命令行 |
| `Contribution Graph/dashboard_server.py` | FastAPI 接口与静态页面服务 |
| `Contribution Graph/dashboard/` | 看板页面、样式与交互 |
| `Contribution Graph/schema.sql` | 数据库表、外键和索引 |
| `Contribution Graph/data.json` | 合并后的项目数据快照 |

目前快照含 1 个项目、4 名成员、4 项任务、6 条贡献，以及对应的核验和争议记录。运行时以 `data.sqlite3` 为准；更改数据后，运行 `python3 export_json.py` 更新快照。命令行用法、API 路径和完整流程见 [详细文档](Contribution%20Graph/README.md)。

## 测试与开发

在 `Contribution Graph/` 中运行：

```sh
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
.venv/bin/python demo_workflow.py
```

前者运行自动化测试；后者在临时数据库中验证完整贡献流程，不修改网站数据。贡献规范见 [AGENTS.md](AGENTS.md)，历次变更见 [CHANGELOG.md](CHANGELOG.md)。
