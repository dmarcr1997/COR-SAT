MISSION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_mission_file",
            "description": (
                "Read one approved mission, reference, "
                "SDK, or candidate file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": (
                            "Project-relative path to "
                            "an approved readable file."
                        ),
                    },
                },
                "required": [
                    "relative_path",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_in_mission_files",
            "description": (
                "Search approved mission and reference "
                "files for exact text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                    },
                },
                "required": [
                    "query",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_mission_file",
            "description": (
                "Write one required file into the current "
                "mission candidate directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "enum": [
                            "manifest.json",
                            "mission.py",
                        ],
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Complete file contents as plain text. "
                            "For manifest.json, provide valid JSON text."
                        ),
                    },
                },
                "required": [
                    "filename",
                    "content",
                ],
            },
        },
    }
]