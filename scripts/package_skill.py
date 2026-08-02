#!/usr/bin/env python3
"""Package the skill directory into a distributable .skill bundle.

A .skill file is simply a ZIP of the skill directory with SKILL.md at its root.
This replaces an earlier Makefile target that pointed at a machine-specific
interpreter and packager path, so it only ever worked on one person's laptop.
Pure stdlib — no venv, no npm, no external tooling.

The archive is written deterministically (sorted entries, fixed timestamps), so
repackaging unchanged content produces a byte-identical file and doesn't create
noise in git.

Usage:
    python3 scripts/package_skill.py                       # ./delphi-api-safe -> ./dist
    python3 scripts/package_skill.py <src_dir> <out_dir>
"""

import os
import subprocess
import sys
import zipfile

# Build junk and editor/VCS artifacts that must never ship inside a bundle.
EXCLUDE_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "node_modules", ".pytest_cache"}
EXCLUDE_EXACT = {".DS_Store", "Thumbs.db"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".swp", ".orig", ".rej")
# Fixed timestamp keeps the zip reproducible (zip epoch starts at 1980).
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def should_skip(name: str) -> bool:
    return (name in EXCLUDE_EXACT) or name.endswith(EXCLUDE_SUFFIX)


def collect(src: str):
    """Yield (absolute_path, arcname) for every file to include, sorted."""
    found = []
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith("."))
        for fn in sorted(files):
            if should_skip(fn):
                continue
            full = os.path.join(root, fn)
            found.append((full, os.path.relpath(full, src)))
    return sorted(found, key=lambda p: p[1])


def validate(src: str) -> str:
    """SKILL.md must exist at the root with YAML frontmatter declaring name + description."""
    skill_md = os.path.join(src, "SKILL.md")
    if not os.path.isfile(skill_md):
        sys.exit(f"ERROR: {skill_md} not found — a skill bundle needs SKILL.md at its root.")
    text = open(skill_md, encoding="utf-8").read()
    if not text.startswith("---"):
        sys.exit("ERROR: SKILL.md is missing its YAML frontmatter block.")
    end = text.find("\n---", 3)
    if end == -1:
        sys.exit("ERROR: SKILL.md frontmatter block is not terminated.")
    front = text[3:end]
    for field in ("name:", "description:"):
        if field not in front:
            sys.exit(f"ERROR: SKILL.md frontmatter is missing `{field}`.")
    for line in front.splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return os.path.basename(os.path.abspath(src))


def dirty_sources(src: str):
    """Skill files with uncommitted changes, if this is a git repo.

    A bundle built from a dirty tree can't be reproduced from a fresh checkout,
    so warn rather than silently shipping unreviewed code inside the archive.
    Degrades to an empty list when git is unavailable or this isn't a repo.
    """
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", src],
                             capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return []
        return [ln[3:].strip() for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else "delphi-api-safe"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "dist"

    if not os.path.isdir(src):
        sys.exit(f"ERROR: source directory not found: {src}")

    name = validate(src)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{name}.skill")

    files = collect(src)
    if not files:
        sys.exit(f"ERROR: no files to package under {src}")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for full, arc in files:
            info = zipfile.ZipInfo(arc, date_time=FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            # Preserve the executable bit for scripts; 0o644 otherwise.
            mode = 0o755 if os.access(full, os.X_OK) else 0o644
            info.external_attr = (mode & 0xFFFF) << 16
            with open(full, "rb") as fh:
                z.writestr(info, fh.read())

    total = sum(os.path.getsize(f) for f, _ in files)
    print(f"Packaged {name}")
    print(f"  source : {src}")
    print(f"  output : {out_path}  ({os.path.getsize(out_path):,} bytes)")
    print(f"  files  : {len(files)}  ({total:,} bytes uncompressed)")
    for _, arc in files:
        print(f"    {arc}")

    dirty = dirty_sources(src)
    if dirty:
        print()
        print("  WARNING: packaged from a dirty working tree — this bundle cannot be")
        print("  reproduced from a fresh checkout until these are committed:")
        for d in dirty:
            print(f"    {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
