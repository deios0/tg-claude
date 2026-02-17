TOOLS = [
    {
        "name": "save_fact",
        "description": (
            "Remember a fact about the user. Use when the user shares personal info, "
            "preferences, or anything worth remembering for future conversations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category (e.g. preference, health, family, work, hobby)",
                },
                "fact": {
                    "type": "string",
                    "description": "The fact to remember",
                },
            },
            "required": ["category", "fact"],
        },
    },
    {
        "name": "create_reminder",
        "description": (
            "Set a reminder for the user at a specific time. "
            "The bot will proactively send a message when the time comes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Reminder text",
                },
                "due_at": {
                    "type": "string",
                    "description": "When to remind, ISO 8601 format (e.g. 2026-02-18T15:00:00)",
                },
            },
            "required": ["text", "due_at"],
        },
    },
    {
        "name": "get_reminders",
        "description": "Show the user's pending (unsent) reminders.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]
