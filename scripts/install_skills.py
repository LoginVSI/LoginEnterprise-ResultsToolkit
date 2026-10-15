"""Install thin project-local host adapters referencing canonical workflows."""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=["codex", "claude"], required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = root / (".agents" if args.host == "codex" else ".claude") / "skills"
    for canonical in sorted((root / "skills").glob("*/SKILL.md")):
        name = canonical.parent.name
        lines = canonical.read_text(encoding="utf-8").splitlines()
        end = lines.index("---", 1)
        content = (
            "\n".join(lines[: end + 1])
            + f"\n\nRead the canonical workflow at `../../../skills/{name}/SKILL.md`. Shared project rules are in `../../../AGENTS.md`; continuation evidence is in `../../../docs/progress.md`. All calculations use `le-results`.\n"
        )
        target = destination / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Existing custom adapter preserved: {target.relative_to(root)}")
        target.write_text(content, encoding="utf-8")
        print(target.relative_to(root))


if __name__ == "__main__":
    main()
