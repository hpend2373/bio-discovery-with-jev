#!/usr/bin/env python3
"""Invoke the maintained engine; never rebuild it from conversational instructions."""
import argparse
import importlib.util
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--project", default=os.environ.get("BIO_TOPIC_DISCOVERY_ROOT"))
args, remaining = parser.parse_known_args()
if args.project:
    root = Path(args.project).expanduser().resolve()
    if not (root / "bio_topics" / "cli.py").is_file():
        raise SystemExit(f"엔진을 찾을 수 없습니다: {root}")
    sys.path.insert(0, str(root))
else:
    # A skill used from a clone finds that clone; an installed copy uses the package.
    root = next((p for p in Path(__file__).resolve().parents
                 if (p / "bio_topics" / "cli.py").is_file()), None)
    if root is not None:
        sys.path.insert(0, str(root))
    elif importlib.util.find_spec("bio_topics") is None:
        raise SystemExit("엔진을 먼저 pip install -e /path/to/bio-topic-discovery로 설치하거나 --project PATH를 지정하세요.")
from bio_topics.cli import main

raise SystemExit(main(remaining))
