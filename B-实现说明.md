# B：贡献审核实现说明

已完成贡献列表与详情、四类证据引用、同伴确认与调整、争议与解决、错误反馈，以及与 C 看板的数据联动。继续使用原生 HTML/CSS/JavaScript 和现有 FastAPI，不增加前端构建工具。

## 打开与启动

本项目在 `Contribution Graph/` 下创建了 `.venv`，并安装 `requirements.txt` 中的依赖。在该目录中运行：

```sh
.venv/bin/python dashboard_server.py
```

- 审核页面：<http://127.0.0.1:8000/review.html>
- C 看板：<http://127.0.0.1:8000/>
- API 文档：<http://127.0.0.1:8000/docs>

服务默认使用 `Contribution Graph/data.sqlite3`。若要保持这份统一数据库不变，生成一份新的 SQLite 副本用于操作，B 和 C 仍由同一个服务读取：

```sh
.venv/bin/python seed_dashboard.py output/b-demo.sqlite3
.venv/bin/python dashboard_server.py --db output/b-demo.sqlite3
```

生成脚本拒绝覆盖已有文件。第二次演示可以继续使用已有文件，或换一个新的文件名。

## 页面和接口怎样配合

```text
review.html / review.js
       ↓ fetch 请求
dashboard_server.py（字段类型检查、HTTP 错误响应）
       ↓
ContributionStore（成员与状态检查、处理记录、SQLite 保存与事务写入）
       ↓
contribution_engine.py（唯一评分公式）
       ↓
重新读取详情和 Dashboard → 更新 B 页面并通知 C 看板
```

| 操作 | 接口 |
|---|---|
| 获取成员、任务、贡献列表、当前分数 | `GET /api/projects/fintech/dashboard` |
| 查看贡献、证据、审核和争议记录 | `GET /api/contributions/{id}` |
| 添加证据 | `POST /api/contributions/{id}/evidence` |
| 确认、调整、提出争议 | `POST /api/contributions/{id}/reviews` |
| 解决争议 | `POST /api/contributions/{id}/resolve` |
| 分数预览 | `POST /api/contributions/{id}/preview` |

前端使用 Dashboard 的 `contributions` 构建列表，再按 ID 获取详情；不需要另建待办列表接口。列表支持四种状态筛选。

## 分数预览的实现

`ContributionStore.preview_score()` 使用 `dataclasses.replace()` 创建副本，将副本视为通过验证，再使用现有 `contribution_score()` 计算修改前后的分值。原贡献状态、字段和文件都不改变。

返回值包含：

- `currentScore`：按当前状态真正计入团队的分数。
- `proposedScore`：原有字段在通过验证后对应的分值。
- `updatedScore`：调整后可计入的分值。
- `scoreChanged`：调整是否真正改变分数。

例如 40 分的 CORE 贡献还在 PENDING，完成比例从 1 改为 0.8：当前计分为 0，提议分值为 40，预览结果为 32。前端只展示这些后端结果。

详情接口同时增加 `currentScore` 和 `proposedScore`，避免把待验证的 0 分当成提议分值。修改输入、切换贡献或成员后会取消旧预览。只有重新预览且分数改变，才允许提交调整。

## 状态和操作限制

| 状态 | 操作 |
|---|---|
| PENDING | 确认、调整、提出争议 |
| VERIFIED | 提出争议 |
| DISPUTED | 解决争议 |
| RESOLVED | 查看最终结果和历史 |

所有状态都可添加证据引用。确认、调整和解决争议不能由贡献者本人操作；提出争议允许贡献者本人操作，与原有后端规则一致。争议必须有原因，解决必须有结论，质量系数范围为 0.9–1.1，CORE 完成比例范围为 0–1，支持分值非负。

前端根据成员和状态禁用按钮；服务端仍执行所有校验，因此直接调用 API 也不能绕过这些业务规则。请求期间页面锁定相关操作，防止重复点击和切换贡献引发错误操作。错误显示在页面顶部；保存成功但刷新失败会明确提示已经保存，并停止展示旧的可操作详情。

证据、说明与历史文本在展示时进行 HTML 转义；只有 HTTP/HTTPS 引用显示为可点击链接。

## B 和 C 的联动

每次成功写入后，B 重新读取贡献详情和项目 Dashboard。分数、占比和关系图的数据由服务器按最新状态重算。

B 同时写入一个 `localStorage` 更新信号。已经打开的同源 C 看板收到 `storage` 事件后重新请求数据；切回看板也会刷新。这个信号仅通知数据发生变化，不保存业务数据。跨设备或不同浏览器仍可手动刷新看板。

## 测试与验收

在 `Contribution Graph/` 中运行全部测试：

```sh
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
```

新增 `test_review_api.py` 覆盖 CORE 和三种非 CORE 的预览、预览不修改文件、四类证据保存、调整与争议后的分数/关系变化、重新创建服务后数据仍然保留，以及自己的贡献、无效输入和状态流转被拒绝后文件保持不变。

合并后共 38 项自动化测试，全部通过。浏览器验证了证据添加、本人按钮限制、必填原因与结论、确认与争议的 `67 → 70 → 67 → 69` 分数变化、后台看板自动更新、CORE 的 `25 → 20` 调整、修改输入后旧预览失效，以及空列表。已检查手机和桌面断点，没有横向溢出；Codex 内置浏览器的控制台未发现错误。测试使用独立数据副本，仓库内的 `data.json` 未被测试修改。

浏览器演示可以使用初始演示数据中的 c3：

1. 选择 Charlie 和 c3，确认按钮应被禁用。
2. 切换为 Alice，添加一条文字证据，然后确认。Charlie 为 3 分，团队总分从 67 变成 70。
3. 填写原因并提出争议。Charlie 暂停计分，团队总分回到 67。
4. 将支持分值改为 2，填写解决结论，点击预览再解决。团队总分变成 69，历史中保留证据、确认、争议和解决结果。
5. C 看板显示同样结果；重启服务仍能读取这些数据。

另用一条新的 PENDING 贡献测试调整：预览改变分值但不保存，提交调整后变为 VERIFIED；未改变分数不能提交调整。

## 当前范围

成员下拉框是演示身份选择，尚无登录认证。SQLite 保存沿用本地单进程方案，证据保存文字和链接引用，没有文件上传。上述限制与当前项目 MVP 范围一致。
