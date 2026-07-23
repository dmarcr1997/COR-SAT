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


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = (
    PROJECT_ROOT
    / "agents"
    / "prompts"
    / "mission_builder.md"
)

MODEL_NAME = "qwen3:1.7b"

MAX_TOOL_ROUNDS = 10

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
        encoding="utf-8"
    )

    user_message = f"""
Create a mission candidate.

Candidate directory:
{candidate_name}

Mission request:
{mission_request}

Use the provided tools.

You must write:

- candidates/{candidate_name}/manifest.json
- candidates/{candidate_name}/mission.py

Do not print the files instead of writing them.
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

    This is intentionally approximate.
    """

    if hasattr(message, "model_dump_json"):
        return len(message.model_dump_json())

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

    Older temporary interactions are dropped when the
    rough context budget is exceeded.
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
        MAX_WORKING_MEMORY_CHARS - pinned_size
    )

    kept_recent_messages: list[Any] = []
    used_size = 0

    for message in reversed(recent_messages):
        size = message_size(message)

        if used_size + size > remaining_budget:
            break

        kept_recent_messages.append(message)
        used_size += size

    kept_recent_messages.reverse()

    return [
        *pinned_messages,
        *kept_recent_messages,
    ]


# ============================================================
# Ollama
# ============================================================

def call_model(
    messages: list[Any],
) -> ChatResponse:
    trimmed_messages = trim_working_memory(
        messages
    )

    return chat(
        model=MODEL_NAME,
        messages=trimmed_messages,
        tools=MISSION_TOOLS,
        stream=False,

        # Prevent the long "Thinking..." spiral.
        think=False,

        options={
            "temperature": 0.2,
            "top_p": 0.9,
        },

        # Keep the model loaded between tool rounds.
        keep_alive="10m",
    )


# ============================================================
# Tool execution
# ============================================================

def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    if tool_name == "read_mission_file":
        return read_mission_file(
            relative_path=arguments["relative_path"],
        )

    if tool_name == "find_in_mission_files":
        return find_in_mission_files(
            query=arguments["query"],
            max_results=arguments.get(
                "max_results",
                10,
            ),
        )

    if tool_name == "write_mission_file":
        return write_mission_file(
            candidate_name=arguments[
                "candidate_name"
            ],
            filename=arguments["filename"],
            content=arguments["content"],
        )

    raise MissionToolError(
        f"Unknown tool: {tool_name}"
    )


def format_tool_result(result: Any) -> str:
    """
    Convert tool output into compact text for Qwen.

    Large outputs are clipped so one read operation cannot
    consume the whole working-memory budget.
    """

    if isinstance(result, str):
        text = result
    else:
        text = json.dumps(
            result,
            indent=2,
            default=str,
        )

    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text

    removed_characters = (
        len(text) - MAX_TOOL_RESULT_CHARS
    )

    return (
        text[:MAX_TOOL_RESULT_CHARS]
        + "\n\n"
        + f"[Tool result truncated: "
        + f"{removed_characters} characters omitted]"
    )


def make_tool_result_message(
    tool_name: str,
    result: Any,
    *,
    error: bool = False,
) -> dict[str, Any]:
    content = format_tool_result(result)

    if error:
        content = f"TOOL_ERROR\n{content}"

    return {
        "role": "tool",
        "tool_name": tool_name,
        "content": content,
    }


# ============================================================
# Candidate verification
# ============================================================

def verify_candidate_files(
    candidate_name: str,
) -> Path:
    candidate_directory = safe_candidate_path(
        candidate_name
    )

    manifest_path = (
        candidate_directory / "manifest.json"
    )
    mission_path = (
        candidate_directory / "mission.py"
    )

    missing_files: list[str] = []

    if not manifest_path.is_file():
        missing_files.append("manifest.json")

    if not mission_path.is_file():
        missing_files.append("mission.py")

    if missing_files:
        raise RuntimeError(
            "Model finished without creating: "
            + ", ".join(missing_files)
        )

    manifest = verify_manifest(
        manifest_path
    )

    verify_mission_python(
        mission_path
    )

    expected_entrypoint = manifest.get(
        "entrypoint"
    )

    if expected_entrypoint != "mission.py":
        raise RuntimeError(
            "Manifest entrypoint must be mission.py"
        )

    return candidate_directory


def verify_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    try:
        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"manifest.json contains invalid JSON: "
            f"{exc}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Could not read manifest.json: {exc}"
        ) from exc

    if not isinstance(manifest, dict):
        raise RuntimeError(
            "manifest.json must contain a JSON object"
        )

    required_fields = (
        "name",
        "version",
        "entrypoint",
    )

    for field in required_fields:
        value = manifest.get(field)

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise RuntimeError(
                f"Manifest field '{field}' must "
                "be a non-empty string"
            )

    return manifest


def verify_mission_python(
    mission_path: Path,
) -> None:
    try:
        source = mission_path.read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise RuntimeError(
            f"Could not read mission.py: {exc}"
        ) from exc

    if not source.strip():
        raise RuntimeError(
            "mission.py is empty"
        )

    try:
        ast.parse(
            source,
            filename=str(mission_path),
        )
    except SyntaxError as exc:
        raise RuntimeError(
            f"mission.py contains invalid Python: "
            f"{exc.msg} at line {exc.lineno}"
        ) from exc


# ============================================================
# Agent loop
# ============================================================

def run_mission_agent(
    mission_request: str,
    candidate_name: str,
) -> Path:
    messages: list[Any] = build_messages(
        mission_request=mission_request,
        candidate_name=candidate_name,
    )

    total_tool_calls = 0

    for round_number in range(
        1,
        MAX_TOOL_ROUNDS + 1,
    ):
        print(
            f"Agent round "
            f"{round_number}/{MAX_TOOL_ROUNDS}"
        )

        response = call_model(messages)

        # The assistant message contains the tool calls.
        messages.append(response.message)

        tool_calls = (
            response.message.tool_calls or []
        )

        if not tool_calls:
            print(
                "Model finished without requesting "
                "another tool."
            )
            break

        for tool_call in tool_calls:
            total_tool_calls += 1

            tool_name = (
                tool_call.function.name
            )

            arguments = dict(
                tool_call.function.arguments
            )

            print(
                f"Tool: {tool_name}"
            )

            try:
                result = execute_tool(
                    tool_name,
                    arguments,
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

            messages.append(tool_message)

        # Trim after a full tool round so the newest
        # assistant calls and tool results stay together.
        messages = trim_working_memory(
            messages
        )

    else:
        raise RuntimeError(
            "Agent reached the maximum number "
            "of tool rounds"
        )

    candidate_directory = (
        verify_candidate_files(
            candidate_name
        )
    )

    print(
        f"Candidate verified after "
        f"{total_tool_calls} tool calls."
    )

    return candidate_directory