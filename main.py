import os
import shutil
import textwrap

from dotenv import load_dotenv

load_dotenv()

from agent import run_agent


def print_wrapped(label: str, text: str) -> None:
    terminal_width = shutil.get_terminal_size(fallback=(100, 24)).columns
    wrapped_width = max(40, terminal_width - len(label) - 2)
    paragraphs = text.splitlines() or [""]

    for index, paragraph in enumerate(paragraphs):
        prefix = f"{label}: " if index == 0 else " " * (len(label) + 2)

        if not paragraph.strip():
            print(prefix.rstrip())
            continue

        wrapped_lines = textwrap.wrap(
            paragraph,
            width=wrapped_width,
            replace_whitespace=False,
            drop_whitespace=True,
        )

        if not wrapped_lines:
            print(prefix.rstrip())
            continue

        print(prefix + wrapped_lines[0])

        for line in wrapped_lines[1:]:
            print(" " * len(prefix) + line)


def main():
    print("ReAct QA Agent")
    print("Type your question and press Enter.")
    print("Commands: /exit, /quit, /verbose on, /verbose off, /history, /clear")
    print(f"Using provider: {os.getenv("LLM_PROVIDER")}")

    verbose = False
    conversation_history = []

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except EOFError:
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        if user_input in {"/exit", "/quit"}:
            print("Goodbye.")
            break

        if user_input == "/verbose on":
            verbose = True
            print("Verbose tracing enabled.")
            continue

        if user_input == "/verbose off":
            verbose = False
            print("Verbose tracing disabled.")
            continue

        if user_input == "/history":
            if not conversation_history:
                print("No conversation history yet.")
                continue

            for message in conversation_history:
                print_wrapped(message["role"].title(), message["content"])

            continue

        if user_input == "/clear":
            conversation_history.clear()
            print("Conversation history cleared.")
            continue

        try:
            answer = run_agent(
                user_input,
                conversation_history=conversation_history,
                max_iterations=5,
                verbose=verbose,
            )
        except Exception as error:
            print(f"Agent error: {error}")
            continue

        print_wrapped("Agent", answer)
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
