"""Build the committed Codex Game Studios operational plugin payload."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    """Build or check the embedded operational payload."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    plugin = root / "plugins/codex-game-studios"
    sys.path.insert(0, str(plugin / "scripts"))
    from models import PayloadError
    from payload import build_payload

    try:
        manifest = build_payload(root, plugin, check=arguments.check)
    except PayloadError as error:
        print(f"Codex Game Studios payload: STALE ({error})", file=sys.stderr)
        return 1
    if arguments.check:
        print("Codex Game Studios payload: FRESH")
    else:
        print(f"generated codex-game-studios payload {manifest.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
