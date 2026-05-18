"""CLI entry point for the Java Full-Stack Training Agent."""

import os
import sys

from . import ui
from .agent import JavaTrainingAgent


def _check_api_key() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        ui.print_error(
            "ANTHROPIC_API_KEY environment variable is not set.\n"
            "  Export it with:  export ANTHROPIC_API_KEY=sk-ant-..."
        )
        return False
    return True


def _handle_submit_command(agent: JavaTrainingAgent) -> None:
    """Collect multi-line code from the user until they type END on a line by itself."""
    ui.print_info("Paste your Java code below. Type [accent]END[/accent] on a new line when done:")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == "END":
            break
        lines.append(line)

    if lines:
        agent.submit_code("\n".join(lines))
    else:
        ui.print_info("No code submitted.")


def _handle_module_command(agent: JavaTrainingAgent, args: str) -> None:
    arg = args.strip()
    if not arg.isdigit():
        ui.print_error("Usage: /module <number>  (e.g., /module 16)")
        return
    agent.jump_to_module(int(arg))


def run() -> None:
    if not _check_api_key():
        sys.exit(1)

    agent = JavaTrainingAgent()
    name = agent.progress.student_name

    ui.print_welcome(name)

    # First-run name prompt
    if not name:
        try:
            entered = ui.console.input(
                "\n[secondary]What's your name?[/secondary] [muted](or press Enter to skip):[/muted] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            entered = ""
        if entered:
            agent.progress.set_student_name(entered)
            ui.print_success(f"Nice to meet you, {entered}! Let's get started.")
            # Kick off the first interaction
            agent.chat(
                f"Hello! I'm {entered}. Please introduce yourself and start me on Module 1 "
                f"of the curriculum. Give me a proper onboarding overview first."
            )
        else:
            agent.chat(
                "Hello! Please introduce yourself, give me a brief overview of the full "
                "curriculum structure, and then start me on Module 1."
            )
    else:
        position = agent.progress.get_current_position()
        agent.chat(
            f"I'm back. Briefly remind me where I left off (Phase {position['phase']}, "
            f"Module {position['module']}: {position['phase_name']}) and continue my training."
        )

    # Main REPL loop
    while True:
        try:
            raw = ui.prompt_input()
        except (EOFError, KeyboardInterrupt):
            ui.console.print()
            ui.print_info("Session ended. Your progress has been saved. See you next time!")
            break

        text = raw.strip()
        if not text:
            continue

        lower = text.lower()

        if lower in ("/quit", "/exit", "/q"):
            ui.print_info("Session ended. Your progress has been saved. See you next time!")
            break

        elif lower in ("/help", "/h"):
            ui.print_help()

        elif lower in ("/progress", "/p"):
            agent.get_profile_display()

        elif lower in ("/profile",):
            agent.get_profile_display()

        elif lower.startswith("/module "):
            _handle_module_command(agent, text[8:])

        elif lower in ("/exercise", "/ex"):
            agent.request_exercise()

        elif lower in ("/quiz",):
            agent.request_quiz()

        elif lower in ("/submit", "/sub"):
            _handle_submit_command(agent)

        elif lower.startswith("/submit "):
            # Inline code on the same line (short snippets)
            code = text[8:].strip()
            if code:
                agent.submit_code(code)
            else:
                _handle_submit_command(agent)

        elif lower in ("/reset",):
            agent.reset_progress()

        elif lower.startswith("/"):
            # Pass unknown slash commands through to the agent
            agent.chat(text)

        else:
            agent.chat(text)


def main() -> None:
    try:
        run()
    except KeyboardInterrupt:
        ui.console.print()
        ui.print_info("Interrupted. Progress saved.")
        sys.exit(0)


if __name__ == "__main__":
    main()
