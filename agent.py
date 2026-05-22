import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests
import tools.basic_tools
from prompts.registry import PromptRegistry
from tools.tool_wrapper import ToolWrapper


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage: dict | None = None
    elapsed_seconds: float | None = None


class LLMClient(ABC):
    @abstractmethod
    def generate(self, messages: list[dict]) -> LLMResponse:
        pass


class LiteLLMClient(LLMClient):
    def __init__(self):
        self.url = os.getenv("LITELLM_URL", "http://localhost:4000/chat/completions")
        self.model = os.getenv("LITELLM_MODEL", "gemma")

    def generate(self, messages: list[dict]) -> LLMResponse:
        start = time.perf_counter()
        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
            },
            timeout=60,
        )
        elapsed_seconds = time.perf_counter() - start
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            usage=data.get("usage"),
            elapsed_seconds=elapsed_seconds
        )


class OpenAIClient(LLMClient):
    def __init__(self):
        self.url = os.getenv("OPENAI_URL", "https://api.openai.com/v1/chat/completions")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.api_key = os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")

    def generate(self, messages: list[dict]) -> LLMResponse:
        start = time.perf_counter()
        response = requests.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
            },
            timeout=60,
        )
        elapsed_seconds = time.perf_counter() - start
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            usage=data.get("usage"),
            elapsed_seconds=elapsed_seconds
        )


class LLMClientFactory:
    @staticmethod
    def create() -> LLMClient:
        provider = os.getenv("LLM_PROVIDER", "openai").lower()

        if provider == "litellm":
            return LiteLLMClient()

        if provider == "openai":
            return OpenAIClient()

        raise ValueError(f"Unsupported LLM provider: {provider}")


llm_client = LLMClientFactory.create()

SYSTEM_PROMPT_NAMES = [
    "react_extract_system",
    "react_planner_system",
    "react_analyst_system",
    "react_summary_system",
]


def call_llm(messages: list[dict]) -> LLMResponse:
    return llm_client.generate(messages)


def print_token_usage(usage: dict | None, elapsed_seconds: float | None = None) -> None:
    if not usage:
        print("Token usage: unavailable")
        return

    prompt_tokens = usage.get("prompt_tokens", "unknown")
    completion_tokens = usage.get("completion_tokens", "unknown")
    total_tokens = usage.get("total_tokens", "unknown")
    usage_parts = [
        f"prompt={prompt_tokens}",
        f"completion={completion_tokens}",
        f"total={total_tokens}",
    ]

    if isinstance(completion_tokens, int) and elapsed_seconds and elapsed_seconds > 0:
        tokens_per_second = completion_tokens / elapsed_seconds
        usage_parts.append(f"latency={elapsed_seconds:.2f}s")
        usage_parts.append(f"speed={tokens_per_second:.2f} tok/s")

    print("Token usage: " + ", ".join(usage_parts))


def build_system_prompt(prompt_registry: PromptRegistry) -> str:
    rendered_sections = [
        prompt_registry.render(
            name,
            tools=json.dumps(ToolWrapper.catalog(), indent=2),
        )
        for name in SYSTEM_PROMPT_NAMES
    ]

    return "\n\n".join(rendered_sections)


def build_user_message(
    user_input: str,
    conversation_history: list[dict] | None,
    scratchpad: list[str],
) -> str:
    if conversation_history:
        rendered_conversation = "\n".join(
            f"{message['role'].title()}: {message['content']}"
            for message in conversation_history
        )
    else:
        rendered_conversation = "No previous conversation turns."

    rendered_scratchpad = "\n".join(scratchpad) if scratchpad else "No current tool observations."

    return f"""Conversation history:
{rendered_conversation}

Current task scratchpad:
{rendered_scratchpad}

Current user request:
{user_input}"""


def execute_tool_call(tool_call: dict, verbose: bool = True) -> str:
    tool_name = tool_call.get("tool")
    tool_args = tool_call.get("args", {})

    if verbose:
        print(f"Calling tool: {tool_name}")
        print(f"Tool args: {tool_args}")

    observation = ToolWrapper.call(tool_name, tool_args)

    if verbose:
        print(f"Observation: {observation}")

    return f"Observation: tool '{tool_name}' returned: {observation}"


def parse_agent_response(raw_response: str) -> dict:
    cleaned_response = raw_response.strip()

    if cleaned_response.startswith("```"):
        cleaned_response = cleaned_response.removeprefix("```json").removeprefix("```")
        cleaned_response = cleaned_response.removesuffix("```").strip()

    return json.loads(cleaned_response)


def contains_arithmetic_result(text: str) -> bool:
    return bool(
        re.search(
            r"\b\d+(?:\s*[+\-*/]\s*\d+)+\s*=\s*-?\d+(?:\.\d+)?\b",
            text,
        )
    )


def contains_url(text: str) -> bool:
    return bool(re.search(r"https?://\S+", text))


def has_tool_observation(scratchpad: list[str], tool_name: str) -> bool:
    return any(f"Observation: tool '{tool_name}' returned:" in item for item in scratchpad)


def request_requires_calculator(user_input: str) -> bool:
    return bool(re.search(r"\d+(?:\s*[+\-*/]\s*\d+)+", user_input))


def request_requires_date(user_input: str) -> bool:
    normalized = user_input.lower()
    date_terms = [
        "date",
        "day is today",
        "what day",
        "today",
        "tomorrow",
        "yesterday",
    ]

    return any(term in normalized for term in date_terms)


def request_requires_time(user_input: str) -> bool:
    normalized = user_input.lower()
    time_terms = [
        "what time",
        "current time",
        "time is it",
        "hour is it",
    ]

    return any(term in normalized for term in time_terms)


def missing_required_tools(user_input: str, scratchpad: list[str]) -> list[str]:
    required_tools = []

    if request_requires_calculator(user_input):
        required_tools.append("calculator")

    if request_requires_date(user_input):
        required_tools.append("get_date")

    if request_requires_time(user_input):
        required_tools.append("get_time")

    if contains_url(user_input):
        required_tools.append("get_page")

    return [
        tool_name
        for tool_name in required_tools
        if not has_tool_observation(scratchpad, tool_name)
    ]


def run_agent(
    user_input: str,
    conversation_history: list[dict] | None = None,
    max_iterations: int = 5,
    verbose: bool = False,
) -> str:
    prompt_registry = PromptRegistry("prompts")
    scratchpad = []

    for iteration in range(1, max_iterations + 1):
        system_prompt = build_system_prompt(prompt_registry)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": build_user_message(
                    user_input,
                    conversation_history,
                    scratchpad,
                ),
            },
        ]

        llm_response = call_llm(messages)
        raw_response = llm_response.content

        print_token_usage(llm_response.usage, llm_response.elapsed_seconds)

        if verbose:
            print(f"\nIteration {iteration}")
            print(f"LLM response: {raw_response}")

        scratchpad.append(f"Assistant: {raw_response}")

        try:
            response_data = parse_agent_response(raw_response)
        except json.JSONDecodeError:
            scratchpad.append(
                "System correction: the previous assistant response was invalid JSON. "
                "Return exactly one valid JSON object using one of the allowed shapes. "
                "If you are giving a final answer with multiple bullet points, put the "
                "entire bullet list inside the single 'answer' string."
            )

            if verbose:
                print("Rejected response: invalid JSON. Asking model to repair format.")

            continue

        response_type = response_data.get("type")

        if response_type == "final":
            answer = response_data.get("answer", "")
            missing_tools = missing_required_tools(user_input, scratchpad)

            if missing_tools:
                scratchpad.append(
                    "System correction: this request requires tool observations "
                    f"from {', '.join(missing_tools)} before finalizing. Call the "
                    "missing tool or tools first, then answer using their observations."
                )

                if verbose:
                    print(
                        "Rejected final answer: missing required tool observations "
                        f"for {', '.join(missing_tools)}."
                    )

                continue

            if contains_arithmetic_result(answer) and not has_tool_observation(scratchpad, "calculator"):
                scratchpad.append(
                    "System correction: the previous final answer included arithmetic "
                    "results, but no calculator observation exists in the current task. "
                    "Call the calculator tool before finalizing arithmetic results."
                )

                if verbose:
                    print("Rejected final answer: arithmetic result requires calculator observation.")

                continue

            return answer

        if response_type == "tool_call":
            print("Tool used.")
            scratchpad.append(execute_tool_call(response_data, verbose=verbose))

            continue

        if response_type == "tool_calls":
            calls = response_data.get("calls", [])

            if not isinstance(calls, list) or not calls:
                return "Invalid tool_calls response: 'calls' must be a non-empty list."

            for tool_call in calls:
                if not isinstance(tool_call, dict):
                    return "Invalid tool_calls response: each call must be an object."

                print("Tool used.")
                scratchpad.append(execute_tool_call(tool_call, verbose=verbose))

            continue

        return f"Unknown response type: {response_type}"

    return "Agent stopped because it reached the maximum number of iterations."
