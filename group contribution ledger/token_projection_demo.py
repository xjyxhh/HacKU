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
    print(f"Project: {view['project']['name']}    Treasury: {view['project']['treasuryId']}")
    print(f"Previous team score: {view['oldTeamTotal']}    Projected total mint: {view['totalSupply']}")
    conserved = view["oldTeamTotal"] == view["totalSupply"]
    print(f"Conservation (previous total score == projected total mint): {'Yes' if conserved else 'No - see skipped below'}")
    print()

    print("Member comparison")
    print(table(
        ["Member", "Previous score", "Projected balance", "Gross mint", "Paid", "Received"],
        [[row["name"], old_scores[row["memberId"]], row["balance"], row["minted"], row["paid"],
          row["received"]] for row in view["balances"]],
    ))
    print()

    print("Task Budgets")
    print(table(
        ["Task", "Value Type", "MintCap", "Minted", "Reserved", "Available"],
        [[task["id"], task["valueType"], task["mintCap"], task["budget"]["minted"],
          task["budget"]["reserved"], task["budget"]["available"]] for task in view["tasks"]],
        right_from=2,
    ))
    print()

    print("Commission Contracts")
    if view["contracts"]:
        print(table(
            ["Contract", "Principal", "Contractor", "Price", "Verified value", "Status"],
            [[item["id"], item["principalId"], item["contractorId"], item["contractPrice"],
              item["verifiedMintValue"], item["status"]] for item in view["contracts"]],
            right_from=3,
        ))
    else:
        print("  (None)")
    print()

    print("Ledger Events")
    if view["events"]:
        print(table(
            ["Sequence", "Type", "Amount", "From", "To", "Note"],
            [[item["sequence"], item["kind"], item["amount"], item["sourceId"],
              item["destinationId"], item["note"]] for item in view["events"]],
            right_from=2,
        ))
    else:
        print("  (None)")
    print()

    print("Skipped contributions")
    if view["skipped"]:
        print(table(
            ["Contribution", "Type", "Status", "Reason"],
            [[item["contributionId"], item["type"], item["status"], item["reason"]]
             for item in view["skipped"]],
            right_from=99,
        ))
    else:
        print("  (None)")
    print()

    print("How to read these tables")
    print("  · Projected balances equal previous scores: phase one restates existing data without creating value.")
    print("  · Gross mint differs: the principal receives the result value, then pays the contractor under the contract.")
    print("    Alice has gross mint 47, pays 7, and retains 40; the previous model shows only her net score of 40.")
    print("  · SUPPORT maps to commissions: the helped member is principal and the contributor is contractor.")
    print("  · The previous model adds SUPPORT scores to team totals; the projection allocates the same mint internally.")
    print()

    print("Projection assumptions")
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
