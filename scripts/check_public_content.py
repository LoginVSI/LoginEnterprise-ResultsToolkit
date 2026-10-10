"""High-confidence secret/private-content checks without printing matched content."""

import re
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    )
    patterns = [
        r"gh[pousr]_[A-Za-z0-9]{20,}",
        r"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"[A-Za-z]:[\\/]Users[\\/][^\s\"<>]+",
        r"[A-Za-z]:[\\/]personalRepos[\\/]",
        r"https?://[^\s\"<>]*cloudapp\.azure\.com",
        r"bplev[a-z0-9]+\.southcentralus",
    ]
    failures = []
    for name in tracked:
        if name.startswith(".private/"):
            failures.append((name, "tracked private file"))
    for name in sorted(set(paths)):
        if not name or not (root / name).is_file():
            continue
        content = (root / name).read_bytes().decode("utf-8", errors="replace")
        if any(re.search(pattern, content) for pattern in patterns):
            failures.append((name, "possible secret or personal/environment-specific content"))
    for name, reason in failures:
        print(f"{name}: {reason}")
    if failures:
        raise SystemExit(1)
    print(
        "Public-content check passed; no tracked private files or high-confidence secret patterns."
    )


if __name__ == "__main__":
    main()
