"""Core training agent — Anthropic SDK with streaming, caching, and tool use."""

import json
import os
from typing import Any

import anthropic

from .curriculum_prompt import SYSTEM_PROMPT
from .progress import ProgressTracker
from .tools import TOOLS, handle_tool_call
from . import ui

MODEL = "claude-opus-4-7"

# Modules where adaptive thinking is engaged for deeper code evaluation
THINKING_MODULES = set(range(16, 42))  # Oracle DB onwards benefit most


class JavaTrainingAgent:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self._progress = ProgressTracker()
        self._history: list[dict[str, Any]] = []

    @property
    def progress(self) -> ProgressTracker:
        return self._progress

    def _system_messages(self) -> list[dict[str, Any]]:
        """Return the system prompt with prompt caching enabled on the large static block."""
        return [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _should_use_thinking(self, latest_user_message: str) -> bool:
        """Use adaptive thinking for code evaluation and complex assessment tasks."""
        triggers = [
            "/submit", "evaluate", "review my code", "check my code",
            "assess", "grade", "score my",
        ]
        msg_lower = latest_user_message.lower()
        current_mod = self._progress.current_module
        return any(t in msg_lower for t in triggers) or current_mod in THINKING_MODULES

    def chat(self, user_message: str) -> None:
        """Send a user message, stream the response, and handle any tool calls."""
        self._history.append({"role": "user", "content": user_message})

        use_thinking = self._should_use_thinking(user_message)
        extra_kwargs: dict[str, Any] = {}
        if use_thinking:
            extra_kwargs["thinking"] = {"type": "adaptive"}

        self._run_agent_loop(extra_kwargs)

    def _run_agent_loop(self, extra_kwargs: dict[str, Any]) -> None:
        """Agentic loop: stream response, execute tools if needed, continue until done."""
        while True:
            response_content: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            printed_thinking = False

            with self._client.messages.stream(
                model=MODEL,
                max_tokens=8192,
                system=self._system_messages(),
                messages=self._history,
                tools=TOOLS,
                **extra_kwargs,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "thinking":
                            if not printed_thinking:
                                ui.print_thinking_indicator()
                                printed_thinking = True
                        elif block.type == "text":
                            pass  # text streams via content_block_delta
                        elif block.type == "tool_use":
                            tool_calls.append({
                                "id": block.id,
                                "name": block.name,
                                "input_json": "",
                            })

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            ui.stream_token(delta.text)
                        elif delta.type == "input_json_delta" and tool_calls:
                            tool_calls[-1]["input_json"] += delta.partial_json
                        elif delta.type == "thinking_delta":
                            pass  # thinking is internal; we just show the indicator

                    elif event.type == "content_block_stop":
                        pass

                    elif event.type == "message_stop":
                        pass

                final_message = stream.get_final_message()

            ui.stream_end()

            # Rebuild content list from final message for history
            response_content = [
                self._content_block_to_dict(b) for b in final_message.content
            ]
            self._history.append({"role": "assistant", "content": response_content})

            stop_reason = final_message.stop_reason
            if stop_reason != "tool_use":
                break

            # Execute tool calls and feed results back
            tool_results: list[dict[str, Any]] = []
            for tc in tool_calls:
                tool_input = json.loads(tc["input_json"] or "{}")
                ui.print_info(f"Running tool: [accent]{tc['name']}[/accent]")
                result_str = handle_tool_call(tc["name"], tool_input, self._progress)

                # For code evaluation, display a formatted panel
                if tc["name"] == "evaluate_code_submission":
                    result_data = json.loads(result_str)
                    if result_data.get("status") == "ready_for_evaluation":
                        ui.print_info("Evaluating your code submission...")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result_str,
                })

            self._history.append({"role": "user", "content": tool_results})

    def _content_block_to_dict(self, block: Any) -> dict[str, Any]:
        """Convert a content block object to a dict suitable for message history."""
        if hasattr(block, "type"):
            if block.type == "text":
                return {"type": "text", "text": block.text}
            if block.type == "thinking":
                return {"type": "thinking", "thinking": getattr(block, "thinking", "")}
            if block.type == "tool_use":
                return {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
        return {"type": "text", "text": str(block)}

    def get_profile_display(self) -> None:
        profile = self._progress.get_full_profile()
        ui.print_progress_dashboard(profile)

    def jump_to_module(self, module: int) -> None:
        if not 1 <= module <= 41:
            ui.print_error("Module number must be between 1 and 41.")
            return
        # Find which phase this module belongs to
        from .progress import PHASE_MODULE_MAP
        phase = next(
            (p for p, mods in PHASE_MODULE_MAP.items() if module in mods),
            self._progress.current_phase,
        )
        self._progress._data["current_phase"] = phase
        self._progress._data["current_module"] = module
        self._progress._save()
        ui.print_success(f"Jumped to Module {module} (Phase {phase}).")
        # Ask the agent to introduce this module
        self.chat(f"/goto_module {module}")

    def submit_code(self, code: str) -> None:
        """Wrap a code paste into an evaluation request."""
        module = self._progress.current_module
        message = (
            f"Please evaluate my Java code submission for Module {module}.\n\n"
            f"```java\n{code}\n```"
        )
        self.chat(message)

    def request_exercise(self) -> None:
        self.chat("/exercise")

    def request_quiz(self) -> None:
        self.chat("/quiz")

    def reset_progress(self) -> bool:
        if ui.confirm("This will permanently delete all your progress. Are you sure?"):
            self._progress.reset()
            self._history.clear()
            ui.print_success("Progress reset. Starting fresh!")
            return True
        ui.print_info("Reset cancelled.")
        return False
