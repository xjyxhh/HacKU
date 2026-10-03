# HacKU · Contribution Graph

## 撤回与项目生命周期 / Withdrawal and project lifecycle

贡献撤回采用申请与独立成员审批。批准后有效分数归零，原贡献、证据与审核历史仍保留；Token 回收额与未收回欠额应分别核对，欠额不代表已追回。项目“删除”是可恢复归档，归档会隐藏公开项目并拒绝写入，不会物理删除数据。/ Contribution withdrawal requires an independent member decision. Approval sets the effective score to zero while preserving contribution, evidence, and review history. Recovered Tokens and outstanding debt must be distinguished. Project deletion means recoverable archival: archived projects are hidden from public listings and reject writes; records are retained.

当前实现 / Current implementation: 站点管理员创建项目后会初始化独立 Token 账本，但不会自动成为项目成员；成员只有被加入项目后才出现在项目看板和 Token 账本中。旧单账本经校验后复制到 `Contribution Graph/token-ledgers/<项目 ID 完整 SHA-256>.sqlite3`，旧 `/api/token/...` 仅作为原项目兼容入口。看板与 Token 工作台均可切换项目，撤回与退出按项目账本回收 Token 或登记具名欠额；管理员可查看待同步账务并重试。/ A site administrator creates an isolated project ledger without being added as a project member. Members appear in a project dashboard and Token ledger only after they join the project. The legacy ledger is copied and verified under the full SHA-256 project path; old `/api/token/...` routes remain aliases for the original project. The dashboard and Token workbench select projects; withdrawal and exit recover available Tokens or record named debt, with an administrator retry view.

部署前请对同一时点的 `data.sqlite3`、旧 `token.sqlite3` 及全部 `token-ledgers/*.sqlite3` 使用 SQLite Backup API 一起备份，并在副本上演练恢复与迁移。公开 `data.json` 不包含密码、会话或邀请。/ Before deployment, back up the contribution database, legacy ledger, and every project ledger at the same maintenance point with the SQLite Backup API, then rehearse restoration and migration on copies. Public `data.json` excludes passwords, sessions, and invitations.

一个用于记录团队任务贡献、同伴核验与协作关系的本地 Web 应用。项目按 `CORE`（核心）、`SUPPORT`（支持）、`REVIEW`（审查）和 `COORDINATION`（协调）四类贡献计分；待核验或争议中的贡献暂不计分。项目面向 HacKU 2026 原型演示，适合可信团队在本机使用。

## 在线访问

[PocketBay 上的 HacKU](https://hacku.pocketbay.app) · [贡献审核](https://hacku.pocketbay.app/review.html) · [Token 工作台](https://hacku.pocketbay.app/token.html)

PocketBay 使用 `/data` 持久卷保存贡献与 Token 两份 SQLite 数据库。账号写入由成员会话认证；首次部署可为一个全局站点管理员生成一次性引导账号文件，站点管理员不自动加入任何项目。邀请链接由项目管理员创建并自行交给成员。公平规则见 `/fairness.html`。

部署压缩包可用 `python3 scripts/package_pocketbay.py /tmp/hacku-pocketbay.zip` 生成。脚本仅打包应用源码、页面及数据快照，并将压缩包中的应用目录命名为 `contribution_graph`，以兼容 PocketBay 当前对带空格目录生成的构建路径。

## 功能

- **贡献录入**：在看板中创建或切换项目、添加成员和任务、提交四类贡献；新贡献以「待验证」状态出现，提交后得分为 0。
- **贡献审核**：独立的审核页面可为贡献添加证据、同伴确认或调整分值、提出及解决争议，并保留完整的核验与争议记录；调整前先预览分数，确认分数实际变化后才提交。
- **项目看板**：查看团队总分、成员得分及占比、任务价值和贡献明细。
- **协作关系图**：展示「成员 → 贡献 → 任务」关系，以虚线标出受帮助成员，并与明细、成员和任务筛选联动；支持按类型、状态、得分和成员排序。
- **中英双语**：页头「设置」可在中文与 English 之间切换，选择保存在当前浏览器。
- **Token 认定**：启用匹配项目的账本后，看板以持久 Token 余额显示成员认定结果，并保留旧贡献分作对照；漏铸可从工作台补同步。
- **账本操作**：迁移已核验的历史贡献，管理任务预算、直接铸币、转账、委托合约、冻结与释放、事件记录及待追偿债务。
- **数据存储**：旧贡献与 Token 账本分别使用 SQLite 文件，默认服务地址为 `http://127.0.0.1:8000`。

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
- [Token 工作台](http://127.0.0.1:8000/token.html) — 余额、预算、委托、事件与补同步。
- [API 文档](http://127.0.0.1:8000/docs) — 交互式接口说明。

`import_json.py` 仅用于首次初始化，已有 `data.sqlite3` 时无需再次导入；它不会覆盖已有数据库。SQLite 文件不进入 Git；仓库中的 `data.json` 是可移植的数据快照。服务默认只监听 `127.0.0.1:8000`，可用 `dashboard_server.py --port 端口`、`--db 路径`、`--token-db 路径` 调整。浏览器代码无需构建。

身份库在应用启动时以增量方式添加。使用 `python3 Contribution\ Graph/manage_auth.py bootstrap-seed --db /绝对路径/data.sqlite3 --member 成员ID --out /tmp/hacku-auth-seed.json` 生成只含 scrypt 哈希的全局管理员引导文件（旧的 `--project` 参数仍可保留），并通过部署包的 `--bootstrap-seed` 选项传入。部署后移除引导文件。密码至少 8 位，并包含英文大写、小写字母和数字；登录使用 HttpOnly 会话 Cookie 和 CSRF 令牌。

新部署必须先按上文配置一次性管理员引导文件。成员登录后才能写入；项目与账本管理操作还需项目管理员权限。会话使用 HttpOnly Cookie，同源写入附带 CSRF 校验。

## 推荐使用流程

1. 在看板选择现有项目，或创建项目、成员及带价值的任务。
2. 提交贡献并添加证据。新贡献为 `PENDING`，当前得分为 0。
3. 在审核页由另一名成员确认、调整或提出争议；调整前可预览分数。争议解决后保留完整记录。
4. 在 Token 工作台迁移该项目已核验的历史贡献，或创建空账本。当前工作台操作活动账本；操作前核对项目 ID。后端在贡献审核同步时会把旧单账本复制、校验并登记到对应项目文件。
5. 查看余额、预算和事件；未同步的已审核贡献可在工作台补同步。争议降分而余额不足时，可在余额恢复后追偿欠额。

Token 迁移会跳过待核验和争议中的贡献；已核验贡献无法完整映射时会失败。历史 `SUPPORT` 贡献在有真实独立审核人时映射为委托合约。详细规则和操作示例见 [应用文档](Contribution%20Graph/README.md)。

## 项目结构

| 路径 | 作用 |
|---|---|
| `Contribution Graph/contribution_engine.py` | 数据模型、校验和评分规则 |
| `Contribution Graph/contribution_store.py` | SQLite 读写、业务流程与命令行 |
| `Contribution Graph/dashboard_server.py` | FastAPI 接口与静态页面服务 |
| `Contribution Graph/dashboard/` | 看板、审核页与 Token 工作台的页面代码 |
| `Contribution Graph/token_engine.py`、`token_store.py` | Token 规则、账本持久化与委托结算 |
| `Contribution Graph/migrate_token_ledger.py` | 已核验历史贡献的 Token 迁移 |
| `Contribution Graph/token_projection_demo.py` | 旧分数与 Token 余额的对照脚本 |
| `Contribution Graph/schema.sql` | 数据库表、外键和索引 |
| `Contribution Graph/data.json` | 合并后的项目数据快照 |
| `Contribution Graph/import_json.py`、`export_json.py`、`merge_sqlite.py` | 快照导入、导出与历史数据库合并工具 |
| `融合指南.md` | 新旧引擎的概念映射、融合陷阱与路线图 |

目前快照含 1 个项目、4 名成员、4 项任务、6 条贡献，以及对应的核验和争议记录。运行时以 `data.sqlite3` 为准；更改数据后，运行 `python3 export_json.py` 更新快照。命令行用法、API 路径和完整流程见 [详细文档](Contribution%20Graph/README.md)，审核页面的实现与验收步骤见 [B-实现说明.md](B-实现说明.md)。

## 贡献与 Token

旧贡献分保留为审核估值；匹配项目的 Token 账本建立后，看板成员卡片显示持久账本余额。审核会尝试铸币或冻结；若写入失败，看板列出待补同步贡献，可在 Token 工作台重试。两份 SQLite 文件不是同一事务，因此补同步状态需要留意。

`data.sqlite3` 存放贡献与审核记录，`token.sqlite3` 存放持久 Token 账本。备份时应同时保存两份数据库，或在 `Contribution Graph/` 运行 `.venv/bin/python export_json.py` 导出包含账本的 JSON 快照。导入含 `token_ledger` 的快照会同时恢复 `token.sqlite3`。运行中的数据可能已与仓库里的示例 `data.json` 不同；更新快照前请确认要发布哪些数据。

写接口使用成员会话、同源 `Origin` 与 CSRF 校验；管理员通过一次性 scrypt seed 初始化，项目管理员可以邀请已加入项目且没有账号的成员。委托需第三方真实批准。已结算争议须先冻结合约付款，再由非当事人管理员释放、退款或拆分。规则与边界见 [FAIRNESS.md](FAIRNESS.md)。

```sh
cd 'Contribution Graph'
.venv/bin/python token_projection_demo.py                # 对照报告（临时库）
.venv/bin/python token_projection_demo.py --db data.sqlite3
.venv/bin/python contribution_store.py token-view fintech # 投影 JSON
.venv/bin/python seed_token_demo.py /tmp/hacku-token-demo # 新建多案例演示库，拒绝覆盖已有数据库
```

服务启动后也可读取 `GET /api/projects/{project_id}/token-view`；`GET /api/dashboard` 的成员数据额外带 `balances`。融合的完整映射规则、陷阱与后续路线见 [融合指南.md](融合指南.md)。

## 测试与开发

在 `Contribution Graph/` 中运行：

```sh
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
.venv/bin/python demo_workflow.py
```

前者覆盖评分引擎、SQLite 持久化、Dashboard 与审核 API、Token 账本及同步；后者在临时数据库中验证完整贡献流程，不修改网站数据。贡献规范见 [AGENTS.md](AGENTS.md)，历次变更见 [CHANGELOG.md](CHANGELOG.md)。
