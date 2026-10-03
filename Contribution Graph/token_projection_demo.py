"""Compare legacy contribution scores with the stage-1 token projection.

Runs on a temporary demo database by default, so the website data is untouched:

    python3 token_projection_demo.py
    python3 token_projection_demo.py --db data.sqlite3
    python3 token_projection_demo.py --json
"""

import argparse
import json
import tempfile
import unicodedata
from pathlib import Path

from contribution_store import ContributionStore
from seed_dashboard import seed


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in str(text))


def pad(text, width, right=False):
    text = str(text)
    spaces = " " * max(1, width - display_width(text))
    return spaces + text if right else text + spaces


def table(headers, rows, right_from=1):
    widths = [max([display_width(header)] + [display_width(row[index]) for row in rows])
              for index, header in enumerate(headers)]
    lines = ["  ".join(pad(header, widths[index], index >= right_from)
                       for index, header in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    for row in rows:
        lines.append("  ".join(pad(value, widths[index], index >= right_from)
                               for index, value in enumerate(row)))
    return "\n".join(lines)


def report(view):
    old_scores = {row["memberId"]: row["totalScore"] for row in view["oldScores"]}
    print(f"项目: {view['project']['name']}    金库: {view['project']['treasuryId']}")
    print(f"旧口径团队总分: {view['oldTeamTotal']}    新口径总铸币: {view['totalSupply']}")
    conserved = view["oldTeamTotal"] == view["totalSupply"]
    print(f"会计守恒 (旧总分 == 新总铸币): {'是' if conserved else '否 —— 见下方 skipped'}")
    print()

    print("成员对照")
    print(table(
        ["成员", "旧分数", "新余额", "毛铸币", "已支付", "已收到"],
        [[row["name"], old_scores[row["memberId"]], row["balance"], row["minted"], row["paid"],
          row["received"]] for row in view["balances"]],
    ))
    print()

    print("任务预算")
    print(table(
        ["任务", "价值类型", "MintCap", "已铸", "已预留", "可用"],
        [[task["id"], task["valueType"], task["mintCap"], task["budget"]["minted"],
          task["budget"]["reserved"], task["budget"]["available"]] for task in view["tasks"]],
        right_from=2,
    ))
    print()

    print("委托合约")
    if view["contracts"]:
        print(table(
            ["合约", "委托人", "执行人", "价格", "验收价值", "状态"],
            [[item["id"], item["principalId"], item["contractorId"], item["contractPrice"],
              item["verifiedMintValue"], item["status"]] for item in view["contracts"]],
            right_from=3,
        ))
    else:
        print("  （无）")
    print()

    print("账本事件")
    if view["events"]:
        print(table(
            ["序", "类型", "金额", "从", "到", "说明"],
            [[item["sequence"], item["kind"], item["amount"], item["sourceId"],
              item["destinationId"], item["note"]] for item in view["events"]],
            right_from=2,
        ))
    else:
        print("  （无）")
    print()

    print("未投影的贡献")
    if view["skipped"]:
        print(table(
            ["贡献", "类型", "状态", "原因"],
            [[item["contributionId"], item["type"], item["status"], item["reason"]]
             for item in view["skipped"]],
            right_from=99,
        ))
    else:
        print("  （无）")
    print()

    print("怎么读这张表")
    print("  · 新余额与旧分数一致，说明阶段一只是把既有数据「重述」成账本，没有凭空造价值。")
    print("  · 差别在「毛铸币」：委托人先按成果价值铸币，再按合约付给执行人。")
    print("    例如上面的 Alice 毛铸币 47、支付 7、净余额 40；旧口径只看到她净得 40。")
    print("  · SUPPORT 被还原成「委托人 = 受帮助成员，执行人 = 贡献者」的委托合约。")
    print("  · 旧口径把 SUPPORT 的得分直接加到团队总分；新口径下它来自同一笔铸币的内部分配。")
    print()

    print("投影假设")
    for line in view["assumptions"]:
        print(f"  · {line}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="compare an existing SQLite database instead of the temp demo")
    parser.add_argument("--json", action="store_true", help="print the raw projection JSON")
    args = parser.parse_args()

    if args.db:
        if not args.db.is_file():
            parser.error(f"database not found: {args.db}")
        view = ContributionStore(args.db).token_view("fintech")
        report(view)
    else:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.sqlite3"
            seed(path)
            view = ContributionStore(path).token_view("fintech")
            report(view)

    if args.json:
        print()
        print(json.dumps(view, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
