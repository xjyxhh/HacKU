# Contribution Graph：完整数据流程

本文件夹包含本地 SQLite 数据保存、贡献评分、验证与争议处理，以及 Dashboard / Graph 网站。网站和命令行默认共用 `data.sqlite3`，统一从 `http://127.0.0.1:8000` 访问。以下命令均在本文件夹中运行：

```sh
cd 'Contribution Graph'
```

## 一键运行独立流程示例

```sh
python3 demo_workflow.py
```

此命令在临时文件中验证提交、证据、审核、争议与计分流程，不会修改网站使用的数据库。若要保留示例结果，指定一个新文件：

```sh
python3 demo_workflow.py --db workflow.sqlite3
python3 contribution_store.py --db workflow.sqlite3 dashboard fintech
python3 contribution_store.py --db workflow.sqlite3 record c4
```

演示中的成员分数变化如下：

| 阶段 | Alice | Bob | Charlie | David |
|---|---:|---:|---:|---:|
| 全部提交，状态为 `PENDING` | 0 | 0 | 0 | 0 |
| 确认与调整后 | 40 | 20 | 3 | 12 |
| David 的 Support 贡献发生争议 | 40 | 20 | 3 | 4 |
| 争议解决，Support 最终价值为 7 | 40 | 20 | 3 | 11 |

## C：打开 Dashboard、录入贡献与关系图

首次运行时，创建虚拟环境、安装依赖，并启动读取统一数据库的网站：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python dashboard_server.py
```

如果本地没有 `data.sqlite3`，先运行 `.venv/bin/python import_json.py data.json data.sqlite3`。`data.json` 是已合并数据的可移植快照；服务不会在默认路径上悄悄创建空数据库。

浏览器打开 `http://127.0.0.1:8000`，API 文档在 `http://127.0.0.1:8000/docs`。页面可切换或创建项目、添加成员和任务、提交四类贡献；提交后立即从 SQLite 重新读取，显示待验证记录。项目、成员、任务和贡献 ID 需要在数据库中唯一。顶部导航串起总览、录入、关系图和贡献明细。关系图显示每条“成员 → 贡献 → 任务”关系，并以虚线标出受帮助成员；点击贡献可查看详情和评分输入字段。刷新保留当前项目、筛选和选中的贡献。合并后的项目含 4 名成员、4 项任务和 6 条贡献；原有两条同名 `c1` 贡献均保留，其中 Alice 的贡献编号为 `merged-c1`。例如确认 Charlie 的待验证贡献：

页头“设置”可在中文和 English 之间切换界面语言，选择保存在当前浏览器中；项目名称、任务说明、贡献描述等录入内容保持原文。

```sh
python3 contribution_store.py review c3 alice CONFIRM
```

刷新页面后，Charlie 的审查得分变为 3，团队总分从 67 变为 70。页面录入使用以下 FastAPI 接口：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/projects` | 列出可切换的项目 |
| GET | `/api/dashboard` | 读取 `fintech` 项目的 Dashboard 数据 |
| GET | `/api/projects/{project_id}/dashboard` | 读取指定项目数据 |
| GET | `/api/contributions/{contribution_id}` | 读取贡献详情、证据和处理记录 |
| POST | `/api/projects` | 创建项目 |
| POST | `/api/projects/{project_id}/members` | 添加成员 |
| POST | `/api/projects/{project_id}/tasks` | 添加任务 |
| POST | `/api/projects/{project_id}/contributions` | 提交贡献 |
| POST | `/api/contributions/{contribution_id}/evidence` | 添加证据 |
| POST | `/api/contributions/{contribution_id}/reviews` | 确认、调整或提出争议 |
| POST | `/api/contributions/{contribution_id}/resolve` | 解决争议 |

POST 请求使用 JSON 请求体，字段名称与 `contribution_store.py` 中相应方法一致；具体字段和枚举值可在 `/docs` 查看。例如确认一条待验证贡献：

```sh
curl -X POST http://127.0.0.1:8000/api/contributions/c3/reviews \
  -H 'Content-Type: application/json' \
  -d '{"reviewer_id":"alice","decision":"CONFIRM"}'
```

服务默认仅监听本机。当前接口使用请求中的成员 ID，尚无登录身份验证；若要开放给外部用户，需先加入认证，并将 SQLite 存储改为 PostgreSQL 等服务数据库。

## 数据快照与备份

`data.json` 保存合并后的完整项目快照。新环境只需导入一次：

```sh
python3 import_json.py data.json data.sqlite3
```

导入工具拒绝覆盖已有数据库。合并前的两份 SQLite 原库保存在 `data.before-merge-*.sqlite3` 和 `demo.before-merge-*.sqlite3`；SQLite 文件已加入 `.gitignore`。日常修改以 `data.sqlite3` 为准，提交更改前运行 `python3 export_json.py` 更新可移植快照。

## 将来迁移到 PostgreSQL 时

- 保持 `schema.sql` 中的项目、成员、项目成员、任务、贡献、证据、审核和争议关系；不要把关联 ID 存回数组。数据库约束和应用校验都要保留。
- 小数字段目前以 SQLite `TEXT` 保存，读取后转为 Python `Decimal` 计算。迁移时逐项校验，再写入 PostgreSQL `NUMERIC`；不要经过浮点数转换。
- 数据库操作集中在 `contribution_store.py`。换库时替换连接、SQL 占位符和事务实现，尽量保持评分引擎及 API 的输入输出不变。
- 按项目、成员、项目成员、任务、贡献、证据、审核、争议的顺序复制数据；迁移前后比较记录数量、贡献状态和成员分数。审核或争议的状态更新及历史记录必须处于同一事务。
- 当前界面和争议处理按 SQLite 插入顺序读取记录（`rowid`）。迁移历史记录时要保留这个顺序，并在 PostgreSQL 中设置明确的排序列。

## B：贡献审核页面

启动服务后打开 `http://127.0.0.1:8000/review.html`，或点击看板顶部的“贡献审核”。选择当前操作成员和贡献，即可添加证据、确认、预览并调整分数、提出争议、解决争议，以及查看历史记录。成员下拉框是演示身份选择，没有登录认证。

- `PENDING`：其他成员可以确认或调整；项目成员可以填写原因提出争议。
- `VERIFIED`：可以提出争议。
- `DISPUTED`：其他成员填写结论并预览最终分数后解决。
- `RESOLVED`：查看最终结果和处理记录。
- `IMAGE`、`GITHUB_PR` 等证据保存文本或链接引用，没有文件上传。
- 调整前先点击“预览分数”；分数实际变化后才能提交调整。确认使用原有提议分值。
- 页面显示的当前分数、提议分值和调整预览均由后端评分引擎提供。新增 `POST /api/contributions/{contribution_id}/preview` 接口接受 `completion`、`support_value`、`quality`，只计算、不保存。
- 写入后重新获取贡献详情和项目数据，并通知同源浏览器中已经打开的看板自动刷新。也可以手动点击“刷新数据”。

在 `Contribution Graph/` 中启动读取统一数据库的服务（虚拟环境与依赖安装见上文）：

```sh
.venv/bin/python dashboard_server.py
```

如需单独演示，先生成一个不存在的 SQLite 文件，再让 B/C 使用同一份副本：

```sh
.venv/bin/python seed_dashboard.py output/b-demo.sqlite3
.venv/bin/python dashboard_server.py --db output/b-demo.sqlite3
```

详细实现与验收步骤见仓库根目录的 `B-实现说明.md`。

## 手动操作全套流程

每条命令都使用同一个 `--db walkthrough.sqlite3`。若文件已含同名 ID，请换一个文件名或 ID。

### 1. 创建项目、成员和预设任务价值

```sh
python3 contribution_store.py --db walkthrough.sqlite3 create-project fintech 'FinTech Contribution Graph'
python3 contribution_store.py --db walkthrough.sqlite3 add-member fintech alice Alice
python3 contribution_store.py --db walkthrough.sqlite3 add-member fintech bob Bob
python3 contribution_store.py --db walkthrough.sqlite3 add-member fintech david David
python3 contribution_store.py --db walkthrough.sqlite3 add-task fintech recommendation 'Recommendation Engine' 40
python3 contribution_store.py --db walkthrough.sqlite3 add-task fintech deployment Deployment 20
```

### 2. 提交贡献并附上证据

```sh
python3 contribution_store.py --db walkthrough.sqlite3 submit fintech c1 alice recommendation CORE '实现推荐逻辑'
python3 contribution_store.py --db walkthrough.sqlite3 submit fintech c2 david deployment SUPPORT '帮助 Alice 排查部署问题' --support-value 8 --helped-member alice
python3 contribution_store.py --db walkthrough.sqlite3 add-evidence c2 david NOTE '共同排查部署问题的记录'
python3 contribution_store.py --db walkthrough.sqlite3 record c2
```

新贡献始终为 `PENDING`，此时 `scores fintech` 显示得分为 0。`submit` 还支持 `REVIEW` 和 `COORDINATION`；Core 可传 `--completion 0.8`，其余类型可传 `--support-value 8`。证据类型可选 `NOTE`、`URL`、`IMAGE`、`GITHUB_PR`，`reference` 保存说明或链接。

### 3. 验证、调整、争议和解决

```sh
python3 contribution_store.py --db walkthrough.sqlite3 review c1 bob ADJUST --completion 0.8 --note '确认完成度为 80%'
python3 contribution_store.py --db walkthrough.sqlite3 review c2 alice CONFIRM
python3 contribution_store.py --db walkthrough.sqlite3 scores fintech
python3 contribution_store.py --db walkthrough.sqlite3 review c2 alice DISPUTE --note '需要重新确认支持价值'
python3 contribution_store.py --db walkthrough.sqlite3 scores fintech
python3 contribution_store.py --db walkthrough.sqlite3 resolve c2 alice '双方确认最终为 7 分' --support-value 7
python3 contribution_store.py --db walkthrough.sqlite3 record c2
```

`CONFIRM` 和 `ADJUST` 需由其他成员操作，并将待验证贡献改为 `VERIFIED`；`ADJUST` 必须提供 `--completion`、`--support-value` 或 `--quality` 中至少一项，且调整后分数必须实际变化。`DISPUTE` 要求 `--note`，会将贡献改为 `DISPUTED` 并暂停计分。`resolve` 也需由其他成员操作，将其改为 `RESOLVED`，保存最终分值与解决说明。每次读取分数都会根据当前状态重新计算。

### 4. 提供给 C 的 Dashboard / Graph 数据

```sh
python3 contribution_store.py --db walkthrough.sqlite3 dashboard fintech
```

输出为 JSON，包含 `project`、`members`、`tasks`、`contributions` 和 `relationships`。成员包含 `totalScore`、`contributionShare` 和四类 `breakdown`；关系中包含贡献者、受帮助成员、任务、类型、状态和当前得分。`PENDING` 与 `DISPUTED` 的当前得分为 0。C 可直接调用 `ContributionStore("walkthrough.sqlite3").dashboard_data("fintech")` 获取相同结构，无需重复计算分数。

## 检查

```sh
python3 -m unittest discover -s . -p 'test_*.py'
```

## 修改代码时

- `contribution_engine.py` 定义数据模型、输入校验和评分规则；修改评分公式或贡献字段时先改这里。
- `schema.sql` 定义表、外键和索引；`contribution_store.py` 负责 SQLite 事务、验证与争议流程，以及 Dashboard / Graph 输出；新增持久化字段时同步检查 schema、`_load()` 和对应输出。
- `demo_workflow.py` 演示完整流程；修改状态流转或输出格式后运行它，并运行上面的测试。
