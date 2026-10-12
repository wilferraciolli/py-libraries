from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict

# A handler gets the user id (from the URL path, never from the model) and
# the model's arguments, and returns something JSON-serialisable.
ToolHandler = Callable[[str, Dict[str, Any]], Awaitable[Any]]


@dataclass
class Tool:
    """
    One capability the agent may use, e.g. "count this user's todos".

    Tools always run as the user the server passes in: `user_id` is supplied
    by the server, so the model cannot ask about anyone else even if a prompt
    (or a document it retrieved) tells it to.
    """

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema for the arguments
    handler: ToolHandler

    def spec(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
