from tools.registry import TOOL_REGISTRY


class ToolWrapper:
    @staticmethod
    def call(name: str, args: dict) -> str:
        if name not in TOOL_REGISTRY:
            return f"Error: tool '{name}' does not exist."

        tool = TOOL_REGISTRY[name]

        try:
            params = tool["params_model"](**args)
        except Exception as error:
            return f"Validation error for tool '{name}': {error}"

        try:
            return str(tool["func"](params))
        except Exception as error:
            return f"Execution error for tool '{name}': {error}"

    @staticmethod
    def catalog() -> list[dict]:
        return [
            {
                "name": name,
                "description": tool["description"],
                "input_schema": tool["params_model"].model_json_schema(),
            }
            for name, tool in TOOL_REGISTRY.items()
        ]