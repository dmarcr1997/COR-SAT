from __future__ import annotations

import argparse
import sys

from agents.pipeline import run_mission_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a mission candidate."
    )

    parser.add_argument(
        "request",
        help="Plain-language mission request",
    )

    parser.add_argument(
        "--candidate",
        default="candidate-001",
        help="Candidate directory name",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        run_mission_pipeline(
            mission_request=args.request,
            candidate_name=args.candidate,
        )
    except (RuntimeError, ValueError) as exc:
        print(
            f"Mission generation failed: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Created candidate: "
        f"candidates/{args.candidate}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
