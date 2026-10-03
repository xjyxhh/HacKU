"""Package the single FastAPI application for PocketBay deployment."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "Contribution Graph"
INCLUDED_SUFFIXES = {".py", ".sql", ".json", ".txt", ".html", ".css", ".js", ".svg", ".md"}


def package(destination):
    destination = Path(destination).resolve()
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(APP_DIR.rglob("*")):
            if not path.is_file() or path.suffix not in INCLUDED_SUFFIXES:
                continue
            if any(part in {".venv", "venv", "__pycache__", ".cache"} for part in path.parts):
                continue
            if path.name.startswith("test_"):
                continue
            archive.write(path, Path("contribution_graph") / path.relative_to(APP_DIR))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(package(args.destination))
