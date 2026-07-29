from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from ollama import ChatResponse, chat

from agents.tools.tool_schemas import MISSION_TOOLS
from agents.tools.tools import (
    MissionToolError,
    find_in_mission_files,
    read_mission_file,
    safe_candidate_path,
    write_mission_file,
)
from runner.validator import (
    MissionValidationError,
    validate_mission,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROMPT_PATH = (
    PROJECT_ROOT
    / "agents"
    / "prompts"
    / "mission_builder.md"
)

MODEL_NAME = "qwen3:4b-instruct"

MAX_TOOL_ROUNDS = 12

# Rough character limit, not an exact token limit.
MAX_WORKING_MEMORY_CHARS = 24_000

# Prevent one file read/search result from flooding context.
MAX_TOOL_RESULT_CHARS = 6_000


# ============================================================
# Messages
# ============================================================

def build_messages(
    mission_request: str,
    candidate_name: str,
) -> list[dict[str, Any]]:
    system_prompt = PROMPT_PATH.read_text(
        encoding="utf-8",
    )

    user_message = f"""
Candidate: {candidate_name}

Mission request:
{mission_request}

Use the workflow status provided by the controller.

Read every required reference exactly once.

The controller has already created manifest.json.

After all required references are read:

1. Write mission.py
2. Stop

Do not write or modify manifest.json.
Do not print file contents.
Do not respond with plain text while mission.py is missing.
""".strip()

    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]


def message_size(message: Any) -> int:
    """
    Estimate how much context a message consumes.
    """

    if hasattr(message, "model_dump_json"):
        return len(
            message.model_dump_json()
        )

    try:
        return len(
            json.dumps(
                message,
                default=str,
            )
        )
    except TypeError:
        return len(str(message))


def trim_working_memory(
    messages: list[Any],
) -> list[Any]:
    """
    Keep:

    - the system prompt
    - the original user request
    - the most recent agent/tool activity
    """

    if len(messages) <= 2:
        return messages

    pinned_messages = messages[:2]
    recent_messages = messages[2:]

    pinned_size = sum(
        message_size(message)
        for message in pinned_messages
    )

    remaining_budget = (
        MAX_WORKING_MEMORY_CHARS
        - pinned_size
    )

    kept_recent_messages: list[Any] = []
    used_size = 0

    for message in reversed(
        recent_messages
    ):
        size = message_size(message)

        if (
            used_size + size
            > remaining_budget
        ):
            break

        kept_recent_messages.append(
            message
        )
        used_size += size

    kept_recent_messages.reverse()

    return [
        *pinned_messages,
        *kept_recent_messages,
    ]


def build_workflow_status(
    required_reads: set[str],
    read_files: set[str],
    required_files: set[str],
    written_files: set[str],
) -> str:
    """
    Tell the model exactly where it is
    in the workflow.
    """

    lines = [
        "Mission workflow status:",
        "",
        "Required references:",
    ]

    for path in sorted(required_reads):
        status = (
            "read"
            if path in read_files
            else "missing"
        )

        lines.append(
            f"- [{status}] {path}"
        )

    lines.extend(
        [
            "",
            "Required output files:",
        ]
    )

    for filename in sorted(
        required_files
    ):
        status = (
            "written"
            if filename in written_files
            else "missing"
        )

        lines.append(
            f"- [{status}] {filename}"
        )

    unread_files = (
        required_reads
        - read_files
    )

    missing_files = (
        required_files
        - written_files
    )

    lines.append("")

    if unread_files:
        next_file = sorted(
            unread_files
        )[0]

        lines.extend(
            [
                "Next required action:",
                (
                    "Call read_mission_file for "
                    f"{next_file}."
                ),
                (
                    "Do not write output files "
                    "yet."
                ),
                (
                    "Do not respond with plain "
                    "text."
                ),
            ]
        )

    elif "manifest.json" in missing_files:
        lines.extend(
            [
                "Controller error:",
                (
                    "manifest.json has not been "
                    "created."
                ),
                (
                    "Do not attempt to create "
                    "manifest.json."
                ),
            ]
        )

    elif "mission.py" in missing_files:
        lines.extend(
            [
                (
                    "All required references "
                    "have been read."
                ),
                (
                    "manifest.json was created "
                    "by the controller."
                ),
                "Next required action:",
                (
                    "Call write_mission_file for "
                    "mission.py."
                ),
                (
                    "Do not read any more files."
                ),
                (
                    "Do not respond with plain "
                    "text."
                ),
            ]
        )

    else:
        lines.extend(
            [
                (
                    "The mission package files "
                    "are complete."
                ),
                (
                    "Respond exactly: "
                    "Mission candidate created."
                ),
            ]
        )

    return "\n".join(lines)


# ============================================================
# Manifest generation
# ============================================================

def build_manifest(
    mission_request: str,
) -> dict[str, Any]:
    request_lower = (
        mission_request.lower()
    )

    permissions: list[str] = []

    if (
        "capture" in request_lower
        or "image" in request_lower
        or "camera" in request_lower
    ):
        permissions.append(
            "camera.capture"
        )

    maximum_captures: int | None = None

    if "20 images" in request_lower:
        maximum_captures = 20

    elif "twenty images" in request_lower:
        maximum_captures = 20

    elif "five images" in request_lower:
        maximum_captures = 5

    elif "5 images" in request_lower:
        maximum_captures = 5

    elif "one image" in request_lower:
        maximum_captures = 1

    elif "1 image" in request_lower:
        maximum_captures = 1

    capture_interval_seconds = 1.0

    if (
        "two-second" in request_lower
        or "two second" in request_lower
        or "2-second" in request_lower
        or "2 second" in request_lower
    ):
        capture_interval_seconds = 2.0

    elif (
        "one-second" in request_lower
        or "one second" in request_lower
        or "1-second" in request_lower
        or "1 second" in request_lower
    ):
        capture_interval_seconds = 1.0

    return {
        "schema_version": 1,
        "name": "generated-mission",
        "version": "0.1.0",
        "entrypoint": "mission.py",
        "permissions": permissions,
        "configuration": {
            "capture_interval_seconds": (
                capture_interval_seconds
            ),
            "request_timeout_seconds": 30,
            "maximum_captures": (
                maximum_captures
            ),
        },
    }


def write_generated_manifest(
    mission_request: str,
    candidate_name: str,
) -> None:
    manifest = build_manifest(
        mission_request
    )

    write_mission_file(
        candidate_name=candidate_name,
        filename="manifest.json",
        content=(
            json.dumps(
                manifest,
                indent=2,
            )
            + "\n"
        ),
    )


# ============================================================
# Ollama
# ============================================================

def call_model(
    messages: list[Any],
) -> ChatResponse:
    trimmed_messages = (
        trim_working_memory(
            messages
        )
    )

    return chat(
        model=MODEL_NAME,
        messages=trimmed_messages,
        tools=MISSION_TOOLS,
        stream=False,
        think=False,
        options={
            "temperature": 0.2,
            "top_p": 0.9,
        },
        keep_alive="10m",
    )


# ============================================================
# Tool execution
# ============================================================

def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    candidate_name: str,
    read_files: set[str],
    written_files: set[str],
) -> Any:
    if tool_name == "read_mission_file":
        relative_path = arguments[
            "relative_path"
        ]

        if relative_path in read_files:
            return {
                "ok": False,
                "code": "FILE_ALREADY_READ",
                "message": (
                    f"{relative_path} was "
                    "already read. Do not read "
                    "it again. Continue to the "
                    "next required action."
                ),
            }

        result = read_mission_file(
            relative_path=relative_path,
        )

        read_files.add(
            relative_path
        )

        return result

    if tool_name == "find_in_mission_files":
        return find_in_mission_files(
            query=arguments["query"],
            max_results=arguments.get(
                "max_results",
                10,
            ),
        )

    if tool_name == "write_mission_file":
        filename = arguments[
            "filename"
        ]

        if filename == "manifest.json":
            raise MissionToolError(
                (
                    "manifest.json is "
                    "controller-managed. "
                    "Write mission.py instead."
                )
            )

        if filename != "mission.py":
            raise MissionToolError(
                (
                    "The mission builder may "
                    "only write mission.py."
                )
            )

        result = write_mission_file(
            candidate_name=candidate_name,
            filename=filename,
            content=arguments["content"],
        )

        written_files.add(
            filename
        )

        return result

    raise MissionToolError(
        f"Unknown tool: {tool_name}"
    )


def format_tool_result(
    result: Any,
) -> str:
    """
    Convert tool output into compact text
    for Qwen.
    """

    if isinstance(result, str):
        text = result
    else:
        text = json.dumps(
            result,
            indent=2,
            default=str,
        )

    if (
        len(text)
        <= MAX_TOOL_RESULT_CHARS
    ):
        return text

    removed_characters = (
        len(text)
        - MAX_TOOL_RESULT_CHARS
    )

    return (
        text[
            :MAX_TOOL_RESULT_CHARS
        ]
        + "\n\n"
        + (
            "[Tool result truncated: "
            f"{removed_characters} "
            "characters omitted]"
        )
    )


def make_tool_result_message(
    tool_name: str,
    result: Any,
    *,
    error: bool = False,
) -> dict[str, Any]:
    content = format_tool_result(
        result
    )

    if error:
        content = (
            f"TOOL_ERROR\n{content}"
        )

    return {
        "role": "tool",
        "tool_name": tool_name,
        "content": content,
    }


def normalize_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if (
        tool_name
        != "write_mission_file"
    ):
        return arguments

    normalized = dict(arguments)

    if "filename" not in normalized:
        possible_filename = (
            normalized.get(
                "candidate_name"
            )
        )

        if possible_filename in {
            "manifest.json",
            "mission.py",
        }:
            normalized["filename"] = (
                possible_filename
            )

    normalized.pop(
        "candidate_name",
        None,
    )

    return normalized


# ============================================================
# Candidate verification
# ============================================================

def verify_candidate_files(
    candidate_name: str,
) -> Path:
    candidate_directory = (
        safe_candidate_path(
            candidate_name
        )
    )

    manifest_path = (
        candidate_directory
        / "manifest.json"
    )

    mission_path = (
        candidate_directory
        / "mission.py"
    )

    missing_files: list[str] = []

    if not manifest_path.is_file():
        missing_files.append(
            "manifest.json"
        )

    if not mission_path.is_file():
        missing_files.append(
            "mission.py"
        )

    if missing_files:
        raise RuntimeError(
            (
                "Mission package is missing: "
                + ", ".join(
                    missing_files
                )
            )
        )

    try:
        validate_mission(
            candidate_directory
        )

    except MissionValidationError as exc:
        formatted_issues = "\n".join(
            f"- {issue.format()}"
            for issue in exc.issues
        )

        raise RuntimeError(
            (
                "Generated mission failed "
                "validation:\n"
                f"{formatted_issues}"
            )
        ) from exc

    verify_mission_python(
        mission_path
    )

    return candidate_directory


def verify_mission_python(
    mission_path: Path,
) -> None:
    try:
        source = (
            mission_path.read_text(
                encoding="utf-8",
            )
        )

    except OSError as exc:
        raise RuntimeError(
            (
                "Could not read mission.py: "
                f"{exc}"
            )
        ) from exc

    if not source.strip():
        raise RuntimeError(
            "mission.py is empty"
        )

    try:
        ast.parse(
            source,
            filename=str(
                mission_path
            ),
        )

    except SyntaxError as exc:
        raise RuntimeError(
            (
                "mission.py contains invalid "
                "Python: "
                f"{exc.msg} at line "
                f"{exc.lineno}"
            )
        ) from exc


# ============================================================
# Agent loop
# ============================================================

def run_mission_agent(
    mission_request: str,
    candidate_name: str,
) -> Path:
    read_files: set[str] = set()
    written_files: set[str] = set()

    required_reads = {
        (
            "agents/references/"
            "mission_contract.md"
        ),
        (
            "agents/references/"
            "sdk_contract.md"
        ),
    }

    if (
        "optical flow"
        in mission_request.lower()
    ):
        required_reads.add(
            (
                "agents/references/"
                "optical_flow_example.md"
            )
        )

    required_files = {
        "manifest.json",
        "mission.py",
    }

    candidate_directory = (
        safe_candidate_path(
            candidate_name
        )
    )

    if candidate_directory.exists():
        raise RuntimeError(
            (
                "Candidate already exists: "
                f"candidates/"
                f"{candidate_name}"
            )
        )

    write_generated_manifest(
        mission_request=mission_request,
        candidate_name=candidate_name,
    )

    written_files.add(
        "manifest.json"
    )

    print(
        "Controller created "
        "manifest.json."
    )

    messages: list[Any] = (
        build_messages(
            mission_request=(
                mission_request
            ),
            candidate_name=(
                candidate_name
            ),
        )
    )

    total_tool_calls = 0

    for round_number in range(
        1,
        MAX_TOOL_ROUNDS + 1,
    ):
        print(
            f"Agent round "
            f"{round_number}/"
            f"{MAX_TOOL_ROUNDS}"
        )

        workflow_status = (
            build_workflow_status(
                required_reads=(
                    required_reads
                ),
                read_files=read_files,
                required_files=(
                    required_files
                ),
                written_files=(
                    written_files
                ),
            )
        )

        messages.append(
            {
                "role": "user",
                "content": (
                    workflow_status
                ),
            }
        )

        response = call_model(
            messages
        )

        messages.append(
            response.message
        )

        tool_calls = (
            response.message.tool_calls
            or []
        )

        if not tool_calls:
            unread_files = (
                required_reads
                - read_files
            )

            missing_files = (
                required_files
                - written_files
            )

            if (
                unread_files
                or missing_files
            ):
                print(
                    (
                        "Model responded without "
                        "a tool before completing "
                        "the workflow."
                    )
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Mission generation "
                            "is incomplete. Follow "
                            "the workflow status "
                            "and call the required "
                            "tool. Do not respond "
                            "with plain text."
                        ),
                    }
                )

                messages = (
                    trim_working_memory(
                        messages
                    )
                )

                continue

            print(
                (
                    "Model completed after "
                    "writing mission.py."
                )
            )

            break

        for tool_call in tool_calls:
            print(
                "RAW TOOL CALL:",
                tool_call.model_dump(),
            )

            total_tool_calls += 1

            tool_name = (
                tool_call.function.name
            )

            arguments = dict(
                tool_call.function.arguments
            )

            arguments = (
                normalize_tool_arguments(
                    tool_name,
                    arguments,
                )
            )

            print(
                f"Tool: {tool_name}"
            )

            try:
                result = execute_tool(
                    tool_name,
                    arguments,
                    candidate_name=(
                        candidate_name
                    ),
                    read_files=(
                        read_files
                    ),
                    written_files=(
                        written_files
                    ),
                )

                tool_message = (
                    make_tool_result_message(
                        tool_name,
                        result,
                    )
                )

            except (
                MissionToolError,
                KeyError,
                TypeError,
                ValueError,
                OSError,
            ) as exc:
                print(
                    f"Tool failed: {exc}"
                )

                tool_message = (
                    make_tool_result_message(
                        tool_name,
                        str(exc),
                        error=True,
                    )
                )

            messages.append(
                tool_message
            )

        messages = (
            trim_working_memory(
                messages
            )
        )

    else:
        raise RuntimeError(
            (
                "Agent reached the maximum "
                "number of tool rounds"
            )
        )

    missing_files = (
        required_files
        - written_files
    )

    if missing_files:
        raise RuntimeError(
            (
                "Mission package is missing "
                "required files: "
                + ", ".join(
                    sorted(
                        missing_files
                    )
                )
            )
        )

    candidate_directory = (
        verify_candidate_files(
            candidate_name
        )
    )

    print(
        (
            "Candidate verified after "
            f"{total_tool_calls} "
            "model tool calls."
        )
    )

    return candidate_directory