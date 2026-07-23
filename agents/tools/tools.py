from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CANDIDATES_ROOT = PROJECT_ROOT / "agents" / "candidates"
ALLOWED_FILENAMES = {
    "manifest.json",
    "mission.py"
}

READABLE_ROOTS = [
    PROJECT_ROOT / "missions",
    PROJECT_ROOT / "sdk",
    PROJECT_ROOT / "agents" / "prompts",
    PROJECT_ROOT / "agents" / "references",
    PROJECT_ROOT / "candidates",
]

class MissionToolError(RuntimeError):
    pass

def safe_candidate_path(relative_path: str) -> Path:
    requested_path = (
        CANDIDATES_ROOT / relative_path
    ).resolve()

    candidates_root = CANDIDATES_ROOT.resolve()

    if not requested_path.is_relative_to(
        candidates_root
    ):
        raise MissionToolError(
            "Path must remain inside candidates/"
        )

    return requested_path
def safe_read_path(relative_path: str) -> Path:
    requested_path = (
        PROJECT_ROOT / relative_path
    ).resolve()

    for root in READABLE_ROOTS:
        resolved_root = root.resolve()

        if requested_path.is_relative_to(
            resolved_root
        ):
            return requested_path

    raise MissionToolError(
        "File is outside approved read locations"
    )

def write_mission_file(
        candidate_name: str,
        filename: str,
        content: str
) -> str:
    if filename not in ALLOWED_FILENAMES:
        raise MissionToolError(
            f"Cannot write file: {filename}"
        )

    candidate_directory = safe_candidate_path(
        candidate_name
    )

    candidate_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = safe_candidate_path(
        f"{candidate_name}/{filename}"
    )

    destination.write_text(
        content.rstrip() + "\n",
        encoding="utf-8",
    )

    return f"Wrote {destination.relative_to(PROJECT_ROOT)}"


def read_mission_file(
        relative_path: str
) -> str:
    path = safe_read_path(relative_path)

    if not path.is_file():
        raise MissionToolError(
            f"File does not exist: {relative_path}"
        )
    
    return path.read_text(
        encoding="utf-8"
    )

def find_in_mission_files(
        query: str,
        max_results: int = 10
) -> list[dict[str, object]]:
    if not query.strip():
        raise MissionToolError(
            "Search query cannot be empty"
        )

    results: list[dict[str, object]] = []

    for root in READABLE_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix not in {
                ".py",
                ".json",
                ".md",
                ".txt",
            }:
                continue

            try:
                lines = path.read_text(
                    encoding="utf-8"
                ).splitlines()
            except OSError:
                continue

            for line_number, line in enumerate(
                lines,
                start=1,
            ):
                if query.lower() not in line.lower():
                    continue

                results.append(
                    {
                        "path": str(
                            path.relative_to(
                                PROJECT_ROOT
                            )
                        ),
                        "line": line_number,
                        "text": line.strip(),
                    }
                )

                if len(results) >= max_results:
                    return results

    return results