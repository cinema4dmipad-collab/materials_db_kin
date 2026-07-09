"""Extract .pptx text to UTF-8 Markdown without the markitdown CLI stdout bug on Windows.

The upstream CLI re-encodes markdown with ``sys.stdout.encoding`` when printing, which
mangles non-ASCII text on typical Windows consoles. Writing via ``-o`` or this script
always uses UTF-8.

Usage (from skill root, skill venv):

    venv\\Scripts\\python.exe scripts/pptx_markdown.py "path/to/file.pptx" -o out.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert .pptx to UTF-8 Markdown.")
    parser.add_argument(
        "pptx",
        type=Path,
        help="Input .pptx path",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output .md path (always UTF-8)",
    )
    args = parser.parse_args()

    if not args.pptx.is_file() or args.pptx.suffix.lower() != ".pptx":
        print(f"Error: not a .pptx file: {args.pptx}", file=sys.stderr)
        sys.exit(1)

    from markitdown import MarkItDown

    result = MarkItDown().convert(str(args.pptx))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.markdown, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
