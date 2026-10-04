"""Create the one-time initial account seed without exposing its password."""
import argparse
import getpass
import hashlib
import json
import os
import sqlite3
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("bootstrap-seed")
    seed.add_argument("--db", required=True)
    seed.add_argument("--project", help="optional legacy project identifier")
    seed.add_argument("--member", required=True)
    seed.add_argument("--out", required=True)
    args = parser.parse_args()
    with sqlite3.connect(f"file:{Path(args.db).resolve()}?mode=ro", uri=True) as conn:
        found = conn.execute("SELECT 1 FROM members WHERE id=?", (args.member,)).fetchone()
    if not found:
        parser.error("member does not exist in the database")
    first = getpass.getpass("Initial password (8+ chars, upper/lowercase and number): ")
    valid = (len(first) >= 8 and any(char.islower() for char in first)
             and any(char.isupper() for char in first)
             and any(char.isdigit() for char in first))
    if not valid or first != getpass.getpass("Repeat password: "):
        parser.error("passwords must match, be at least 8 characters, and include uppercase, lowercase, and a number")
    salt = os.urandom(16)
    digest = hashlib.scrypt(first.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    target = Path(args.out)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump({"member_id":args.member,**({"project_id": args.project} if args.project else {}),
                   "password_scheme":"scrypt","scrypt":{"n":2**14,"r":8,"p":1,"dklen":32},
                   "salt":salt.hex(),"password_hash":digest.hex()}, output)
        output.write("\n")
if __name__ == "__main__": main()
