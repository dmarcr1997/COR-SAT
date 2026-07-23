MISSION_TOOLS = [
    {
        "name": "read_mission_file",
        "description": "Read an approved mission, SDK, reference, or candidate file.",
        "parameters": {
            "type": "object",
            "properties": {
            "relative_path": {
                "type": "string"
            }
            },
            "required": ["relative_path"]
        }
    },
    {
        "name": "find_in_mission_files",
        "description": "Search approved files for an exact text pattern.",
        "parameters": {
            "type": "object",
            "properties": {
            "query": {
                "type": "string"
            }
            },
            "required": ["query"]
        }
    },
    {
        "name": "write_mission_file",
        "description": "Write manifest.json or mission.py inside a candidate directory.",
        "parameters": {
            "type": "object",
            "properties": {
            "candidate_name": {
                "type": "string"
            },
            "filename": {
                "type": "string",
                "enum": [
                "manifest.json",
                "mission.py"
                ]
            },
            "content": {
                "type": "string"
            }
            },
            "required": [
            "candidate_name",
            "filename",
            "content"
            ]
        }
    }
]