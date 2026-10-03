# HacKU · Contribution Graph

一个用于记录团队任务贡献、同伴核验与协作关系的 Web 应用。用户注册后进入个人工作区，可创建或加入多个项目；项目成员按 Owner、Member、Verifier、Viewer 角色协作，并通过任务预算、委托合约、独立验证、Token 账本和关系图追溯价值。旧评分模型仍用于已有贡献的兼容与迁移。

## 在线访问

[PocketBay 上的 HacKU](https://hacku.pocketbay.app) · [贡献审核](https://hacku.pocketbay.app/review.html) · [Token 工作台](https://hacku.pocketbay.app/token.html)

PocketBay 使用 `/data` 持久卷保存贡献数据库和 Token 数据库。首次启动从仓库的 `Contribution Graph/data.json` 导入演示数据，后续部署沿用持久卷中的数据。用户可自行注册邮箱与密码；现有项目成员可由项目 Owner 邀请。管理员可设置 `TOKEN_ADMIN_KEY` 作为全项目紧急管理凭据，该密钥应仅由可信运维人员持有。

部署压缩包可用 `python3 scripts/package_pocketbay.py /tmp/hacku-pocketbay.zip` 生成。脚本仅打包应用源码、页面及数据快照，并将压缩包中的应用目录命名为 `contribution_graph`，以兼容 PocketBay 当前对带空格目录生成的构建路径。

## 功能

- **账号与工作区**：注册、登录、编辑 Profile；在工作区区分负责和参与的项目、查看待办及 Token 余额，并创建项目。
- **项目协作**：按项目隔离成员、角色、任务和 Token 子账本；Owner 邀请已注册用户并管理项目角色。
- **贡献录入**：在项目中创建任务、提交四类贡献并附加证据；新贡献以「待验证」状态出现，只有审核后才形成认定。
- **贡献审核**：独立的审核页面可为贡献添加证据、同伴确认或调整分值、提出及解决争议，并保留完整的核验与争议记录；调整前先预览分数，确认分数实际变化后才提交。
- **项目看板**：查看团队总分、成员得分及占比、任务价值和贡献明细。
- **协作关系图**：查看价值创造、Token 流动、协作、验证/信任视图；账本余额可展开到对应事件。
- **中英双语**：页头「设置」可在中文与 English 之间切换，选择保存在当前浏览器。
- **Token 认定**：启用匹配项目的账本后，看板以持久 Token 余额显示成员认定结果，并保留旧贡献分作对照；漏铸可从工作台补同步。
- **账本操作**：每个项目拥有独立 Token 子账本；支持预算、直接铸币、转账、含交付证据的委托合约、独立验证与 Mint-and-Split、冻结/释放、账本追溯及待追偿债务。
- **演示体验**：公开 Demo 可免注册查看项目流程。
- **数据存储**：项目与认证数据使用贡献 SQLite；所有项目的 Token 子账本按 `project_id` 隔离并共存于 `token.sqlite3`，默认服务地址为 `http://127.0.0.1:8000`。

## 快速开始

需要 Python 3。克隆仓库后，在项目目录中执行：

```sh
cd 'Contribution Graph'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python import_json.py data.json data.sqlite3
export TOKEN_ADMIN_KEY='替换为仅管理员知晓的长随机密钥'
.venv/bin/python dashboard_server.py
```

启动后：

- [项目看板](http://127.0.0.1:8000) — 总览、录入、关系图与贡献明细。
- [公开 Demo](http://127.0.0.1:8000/demo.html) — 无需登录查看示例项目。
- [注册](http://127.0.0.1:8000/register.html) — 创建账号与个人工作区。
- [我的项目](http://127.0.0.1:8000/workspace.html) — 创建、切换和查看项目状态。
- [贡献审核](http://127.0.0.1:8000/review.html) — 证据、同伴验证与争议处理。
- [Token 工作台](http://127.0.0.1:8000/token.html) — 余额、预算、委托、事件与补同步。
- [成员登录](http://127.0.0.1:8000/login.html) — 登录或由管理员开通、重置成员账号。
- [API 文档](http://127.0.0.1:8000/docs) — 交互式接口说明。

`import_json.py` 仅用于首次初始化，已有 `data.sqlite3` 时无需再次导入；它不会覆盖已有数据库。SQLite 文件不进入 Git；仓库中的 `data.json` 是可移植的数据快照。服务默认只监听 `127.0.0.1:8000`，可用 `dashboard_server.py --port 端口`、`--db 路径`、`--token-db 路径` 调整。浏览器代码无需构建。

注册后，用户可创建项目并自动成为 Owner。Owner 可用已注册用户的成员 ID 或邮箱邀请成员，分配 Owner、Member、Verifier、Viewer 角色；当前不发送邮件或一次性邀请链接。项目权限由服务端校验：成员不能伪造贡献/审核身份，委托承接人提交交付，项目当事人不能验证自己的委托。

`TOKEN_ADMIN_KEY` 是可选的全项目管理通道，可用于运维和恢复；普通项目操作按成员角色授权。管理员密钥应仅由可信管理员持有。API 使用 `X-Token-Admin-Key` 请求头，例如：

```sh
curl -X POST http://127.0.0.1:8000/api/projects \
  -H 'Content-Type: application/json' \
  -H "X-Token-Admin-Key: $TOKEN_ADMIN_KEY" \
  -d '{"id":"demo","name":"Demo Project"}'
```

未配置管理员密钥时，角色授权的项目操作仍可使用；涉及全局特权的操作不能通过管理员通道执行。成员账号对应全局成员 ID，可加入多个项目；会话通过 HttpOnly Cookie 保存，有效期 7 天。

## 推荐使用流程

1. 注册并完善 Profile，进入工作区创建或选择项目。
2. Owner 邀请成员、设置角色并创建任务及 Mint Cap。
3. 成员提交贡献或创建委托；承接人接受、预留预算并提交交付证据。
4. 非委托双方的 Verifier 审核成果；独立批准后原子铸币和分配。
5. 通过余额明细、账本事件和四类 Graph 视图查看价值来源、协作与验证；争议通过冻结和释放处理。

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

旧贡献分保留为历史估值与迁移输入；看板成员卡片显示 Token 持有量、可用/冻结余额和待铸价值。审核会尝试铸币或冻结；若跨库写入失败，看板会列出待补同步贡献，可在 Token 工作台重试。

`data.sqlite3` 存放贡献与审核记录，`token.sqlite3` 存放持久 Token 账本。备份时应同时保存两份数据库，或在 `Contribution Graph/` 运行 `.venv/bin/python export_json.py` 导出包含账本的 JSON 快照。导入含 `token_ledger` 的快照会同时恢复 `token.sqlite3`。运行中的数据可能已与仓库里的示例 `data.json` 不同；更新快照前请确认要发布哪些数据。

```sh
cd 'Contribution Graph'
.venv/bin/python token_projection_demo.py                # 对照报告（临时库）
.venv/bin/python token_projection_demo.py --db data.sqlite3
.venv/bin/python contribution_store.py token-view fintech # 投影 JSON
```

服务启动后也可读取 `GET /api/projects/{project_id}/token-view`；`GET /api/dashboard` 的成员数据额外带 `balances`。融合的完整映射规则、陷阱与后续路线见 [融合指南.md](融合指南.md)。

## 测试与开发

在 `Contribution Graph/` 中运行：

```sh
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
.venv/bin/python demo_workflow.py
```

前者覆盖评分引擎、SQLite 持久化、Dashboard 与审核 API、Token 账本及同步；后者在临时数据库中验证完整贡献流程，不修改网站数据。贡献规范见 [AGENTS.md](AGENTS.md)，历次变更见 [CHANGELOG.md](CHANGELOG.md)。
