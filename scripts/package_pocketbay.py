"""Package the single FastAPI application for PocketBay deployment."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "Contribution Graph"
INCLUDED_SUFFIXES = {".py", ".sql", ".json", ".txt", ".html", ".css", ".js", ".svg", ".md"}


def package(destination, bootstrap_seed=None):
    destination = Path(destination).resolve()
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(APP_DIR.rglob("*")):
            if not path.is_file() or path.suffix not in INCLUDED_SUFFIXES:
                continue
            if any(part in {".venv", "venv", "__pycache__", ".cache", "private"} for part in path.parts):
                continue
            if path.name.startswith("test_"):
                continue
            archive.write(path, Path("contribution_graph") / path.relative_to(APP_DIR))
        if bootstrap_seed:
            seed = Path(bootstrap_seed).resolve()
            if not seed.is_file():
                raise FileNotFoundError(seed)
            info = ZipInfo("contribution_graph/private/hacku-auth-seed.json")
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, seed.read_bytes())
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--bootstrap-seed", type=Path, help="include a one-time private bootstrap seed")
    args = parser.parse_args()
    print(package(args.destination, args.bootstrap_seed))
