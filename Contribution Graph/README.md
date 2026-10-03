# Contribution Graph：完整数据流程

本文件夹包含本地 JSON 数据保存、贡献评分、验证与争议处理，以及供 Dashboard / Graph 使用的数据输出。命令行数据工具只需 Python 3；网页服务使用 FastAPI。数据工具不指定 `--db` 时使用本文件夹的 `data.json`，网页服务默认使用 `demo.json`。以下命令均在本文件夹中运行：

```sh
cd 'Contribution Graph'
```

## 一键运行完整演示

```sh
python3 demo_workflow.py
```

演示使用 4 位成员、4 项任务和 5 条贡献，依次完成提交、添加证据、确认、调整、争议、解决争议和刷新 Dashboard。默认使用临时数据文件；若想保留结果，使用一个尚不存在的数据文件：

```sh
python3 demo_workflow.py --db demo.json
python3 contribution_store.py --db demo.json dashboard fintech
python3 contribution_store.py --db demo.json record c4
```

演示中的成员分数变化如下：

| 阶段 | Alice | Bob | Charlie | David |
|---|---:|---:|---:|---:|
| 全部提交，状态为 `PENDING` | 0 | 0 | 0 | 0 |
| 确认与调整后 | 40 | 20 | 3 | 12 |
| David 的 Support 贡献发生争议 | 40 | 20 | 3 | 4 |
| 争议解决，Support 最终价值为 7 | 40 | 20 | 3 | 11 |

## C：打开 Dashboard 与帮助关系图

首次运行时，在本文件夹生成固定的四人演示数据，并启动本地只读页面：

```sh
python3 -m pip install -r requirements.txt
python3 seed_dashboard.py
python3 dashboard_server.py
```

浏览器打开 `http://127.0.0.1:8000`，API 文档在 `http://127.0.0.1:8000/docs`。页面显示项目总览、任务价值、成员总分与四类明细、贡献占比、帮助关系图和贡献状态。演示文件 `demo.json` 包含 4 名成员、4 项任务、5 条贡献，以及 `PENDING`、`VERIFIED`、`DISPUTED`、`RESOLVED` 四种状态。`seed_dashboard.py` 不会覆盖已有文件；需要重置演示数据时，先将旧文件移走或删除，再运行脚本。

页面每次点击“刷新数据”都会重新读取同一个 JSON 文件。如果 B 用命令行或自己的界面修改贡献，请确保也使用 `--db demo.json`；例如确认 Charlie 的待验证贡献：

```sh
python3 contribution_store.py --db demo.json review c3 alice CONFIRM
```

刷新页面后，Charlie 的审查得分变为 3，团队总分从 67 变为 70。若 B/C 使用其他数据文件，可用 `python3 dashboard_server.py --db /path/to/shared.json` 启动页面。现有页面仍为只读，但 FastAPI 已提供写入接口供 B 的界面调用：

| 方法 | 路径 | 用途 |
|---|---|---|
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

服务默认仅监听本机。当前接口使用请求中的成员 ID，尚无登录身份验证；若要开放给外部用户，需先加入认证，并将 JSON 存储改为支持多进程事务的数据库。

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

在仓库根目录使用虚拟环境启动（本机已创建 `.venv` 并安装依赖）：

```powershell
.\.venv\Scripts\python.exe "Contribution Graph\dashboard_server.py"
```

如需单独演示，先生成一个不存在的文件，再让 B/C 使用同一份副本：

```powershell
.\.venv\Scripts\python.exe "Contribution Graph\seed_dashboard.py" "output\b-demo.json"
.\.venv\Scripts\python.exe "Contribution Graph\dashboard_server.py" --db "output\b-demo.json"
```

详细实现与验收步骤见仓库根目录的 `B-实现说明.md`。

## 手动操作全套流程

每条命令都使用同一个 `--db walkthrough.json`。若文件已含同名 ID，请换一个文件名或 ID。

### 1. 创建项目、成员和预设任务价值

```sh
python3 contribution_store.py --db walkthrough.json create-project fintech 'FinTech Contribution Graph'
python3 contribution_store.py --db walkthrough.json add-member fintech alice Alice
python3 contribution_store.py --db walkthrough.json add-member fintech bob Bob
python3 contribution_store.py --db walkthrough.json add-member fintech david David
python3 contribution_store.py --db walkthrough.json add-task fintech recommendation 'Recommendation Engine' 40
python3 contribution_store.py --db walkthrough.json add-task fintech deployment Deployment 20
```

### 2. 提交贡献并附上证据

```sh
python3 contribution_store.py --db walkthrough.json submit fintech c1 alice recommendation CORE '实现推荐逻辑'
python3 contribution_store.py --db walkthrough.json submit fintech c2 david deployment SUPPORT '帮助 Alice 排查部署问题' --support-value 8 --helped-member alice
python3 contribution_store.py --db walkthrough.json add-evidence c2 david NOTE '共同排查部署问题的记录'
python3 contribution_store.py --db walkthrough.json record c2
```

新贡献始终为 `PENDING`，此时 `scores fintech` 显示得分为 0。`submit` 还支持 `REVIEW` 和 `COORDINATION`；Core 可传 `--completion 0.8`，其余类型可传 `--support-value 8`。证据类型可选 `NOTE`、`URL`、`IMAGE`、`GITHUB_PR`，`reference` 保存说明或链接。

### 3. 验证、调整、争议和解决

```sh
python3 contribution_store.py --db walkthrough.json review c1 bob ADJUST --completion 0.8 --note '确认完成度为 80%'
python3 contribution_store.py --db walkthrough.json review c2 alice CONFIRM
python3 contribution_store.py --db walkthrough.json scores fintech
python3 contribution_store.py --db walkthrough.json review c2 alice DISPUTE --note '需要重新确认支持价值'
python3 contribution_store.py --db walkthrough.json scores fintech
python3 contribution_store.py --db walkthrough.json resolve c2 alice '双方确认最终为 7 分' --support-value 7
python3 contribution_store.py --db walkthrough.json record c2
```

`CONFIRM` 和 `ADJUST` 需由其他成员操作，并将待验证贡献改为 `VERIFIED`；`ADJUST` 必须提供 `--completion`、`--support-value` 或 `--quality` 中至少一项，且调整后分数必须实际变化。`DISPUTE` 要求 `--note`，会将贡献改为 `DISPUTED` 并暂停计分。`resolve` 也需由其他成员操作，将其改为 `RESOLVED`，保存最终分值与解决说明。每次读取分数都会根据当前状态重新计算。

### 4. 提供给 C 的 Dashboard / Graph 数据

```sh
python3 contribution_store.py --db walkthrough.json dashboard fintech
```

输出为 JSON，包含 `project`、`members`、`tasks`、`contributions` 和 `relationships`。成员包含 `totalScore`、`contributionShare` 和四类 `breakdown`；关系中包含贡献者、受帮助成员、任务、类型、状态和当前得分。`PENDING` 与 `DISPUTED` 的当前得分为 0。C 可直接调用 `ContributionStore("walkthrough.json").dashboard_data("fintech")` 获取相同结构，无需重复计算分数。

## 检查

```sh
python3 -m unittest discover -s . -p 'test_*.py'
```

## 修改代码时

- `contribution_engine.py` 定义数据模型、输入校验和评分规则；修改评分公式或贡献字段时先改这里。
- `contribution_store.py` 负责 JSON 读写、验证与争议流程，以及 Dashboard / Graph 输出；新增持久化字段时同步检查 `_load()` 和对应输出。
- `demo_workflow.py` 演示完整流程；修改状态流转或输出格式后运行它，并运行上面的测试。
