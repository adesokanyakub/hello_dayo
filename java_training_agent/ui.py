"""Rich terminal UI components for the Java Full-Stack Training Agent."""

from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

ORACLE_THEME = Theme({
    "primary": "bold #C74634",       # Oracle red
    "secondary": "bold #00758F",     # Oracle teal
    "accent": "bold #F08000",        # Oracle orange
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "muted": "dim white",
    "code": "bold cyan",
    "phase": "bold #9B59B6",
    "ai": "bold magenta",
})

console = Console(theme=ORACLE_THEME, highlight=True)


def print_welcome(student_name: str = "") -> None:
    greeting = f"Welcome back, [secondary]{student_name}[/secondary]!" if student_name else "Welcome!"

    banner = Panel(
        Text.from_markup(
            f"""[primary]  ╔═══════════════════════════════════════════════╗
  ║   JFST — Java Full-Stack Trainer              ║
  ║   Powered by Oracle Ecosystem + Claude AI     ║
  ╚═══════════════════════════════════════════════╝[/primary]

  {greeting}
  Your journey from Java beginner to AI-augmented
  full-stack developer starts here.

  [muted]Type [accent]/help[/accent] for commands  |  [accent]/progress[/accent] for your dashboard[/muted]""",
            justify="left",
        ),
        border_style="primary",
        padding=(1, 2),
    )
    console.print(banner)


def print_help() -> None:
    table = Table(
        title="[primary]Available Commands[/primary]",
        show_header=True,
        header_style="secondary",
        border_style="dim",
        expand=False,
    )
    table.add_column("Command", style="accent", no_wrap=True)
    table.add_column("Description", style="white")

    commands = [
        ("/help", "Show this help message"),
        ("/progress", "View your learning dashboard"),
        ("/module <N>", "Jump to a specific module (1-41)"),
        ("/exercise", "Generate a practice exercise for current module"),
        ("/quiz", "Take a knowledge quiz for current module"),
        ("/submit", "Submit code for evaluation (paste after command)"),
        ("/profile", "View detailed student profile & recommendations"),
        ("/reset", "Reset all progress (confirmation required)"),
        ("/quit", "Exit the training agent"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)

    console.print(table)


def print_progress_dashboard(profile: dict[str, Any]) -> None:
    console.print(Rule("[primary]Learning Dashboard[/primary]"))

    # Header stats
    position = profile.get("current_position", {})
    phase_name = position.get("phase_name", "")
    overall_pct = profile.get("overall_completion_pct", 0)
    study_mins = profile.get("total_study_minutes", 0)
    sessions = profile.get("session_count", 0)

    stats_table = Table.grid(expand=True, padding=(0, 2))
    stats_table.add_column(justify="center")
    stats_table.add_column(justify="center")
    stats_table.add_column(justify="center")
    stats_table.add_column(justify="center")

    stats_table.add_row(
        _stat_panel("Overall", f"{overall_pct}%", "secondary"),
        _stat_panel("Phase", str(position.get("phase", 1)), "phase"),
        _stat_panel("Sessions", str(sessions), "accent"),
        _stat_panel("Study Time", f"{study_mins // 60}h {study_mins % 60}m", "ai"),
    )
    console.print(stats_table)
    console.print()

    console.print(f"  [secondary]Current:[/secondary] Phase {position.get('phase')} — [phase]{phase_name}[/phase]  "
                  f"| Module [accent]{position.get('module')}[/accent]")
    console.print()

    # Phase progress table
    phase_data = profile.get("phase_progress", [])
    if phase_data:
        p_table = Table(
            title="[primary]Phase Progress[/primary]",
            show_header=True,
            header_style="secondary",
            border_style="dim",
            expand=True,
        )
        p_table.add_column("#", style="muted", width=3)
        p_table.add_column("Phase", style="white")
        p_table.add_column("Progress", min_width=20)
        p_table.add_column("Modules", justify="right", style="muted")
        p_table.add_column("Status", justify="center")

        for p in phase_data:
            bar = _progress_bar(p["pct"])
            status = "[success]✔ Done[/success]" if p["phase_complete"] else (
                "[accent]◑ Active[/accent]" if p["modules_done"] > 0 else "[muted]○ Locked[/muted]"
            )
            p_table.add_row(
                str(p["phase"]),
                p["name"],
                bar,
                f"{p['modules_done']}/{p['modules_total']}",
                status,
            )
        console.print(p_table)

    # Assessment summary
    assessment = profile.get("assessment_summary", {})
    if assessment.get("total", 0) > 0:
        console.print()
        a_table = Table(
            title="[primary]Assessment Summary[/primary]",
            show_header=True,
            header_style="secondary",
            border_style="dim",
        )
        a_table.add_column("Metric", style="white")
        a_table.add_column("Value", style="accent", justify="right")

        a_table.add_row("Total Assessments", str(assessment["total"]))
        a_table.add_row("Average Score", f"{assessment['average']}%")
        a_table.add_row("Pass Rate (≥70%)", f"{assessment['pass_rate']}%")

        for atype, avg in assessment.get("by_type", {}).items():
            label = atype.replace("_", " ").title()
            a_table.add_row(f"  └ {label}", f"{avg}%")

        console.print(a_table)

    # Recommendations
    recs = profile.get("recommendations", [])
    if recs:
        console.print()
        console.print(Panel(
            "\n".join(f"  [accent]→[/accent] {r}" for r in recs),
            title="[primary]Recommendations[/primary]",
            border_style="secondary",
            padding=(0, 1),
        ))

    console.print(Rule(style="dim"))


def _stat_panel(label: str, value: str, style: str) -> Panel:
    return Panel(
        Text.from_markup(f"[{style}]{value}[/{style}]\n[muted]{label}[/muted]", justify="center"),
        border_style=style,
        padding=(0, 1),
    )


def _progress_bar(pct: int) -> Text:
    filled = int(pct / 5)
    empty = 20 - filled
    bar = Text()
    bar.append("█" * filled, style="secondary")
    bar.append("░" * empty, style="muted")
    bar.append(f" {pct}%", style="muted")
    return bar


def print_lesson_header(phase: int, module: int, title: str) -> None:
    console.print()
    console.print(Rule(
        f"[muted]Phase {phase}[/muted] [primary]▸[/primary] [phase]Module {module}[/phase] [primary]▸[/primary] [secondary]{title}[/secondary]",
        style="dim",
    ))
    console.print()


def print_exercise(exercise_content: str) -> None:
    console.print(Panel(
        Markdown(exercise_content),
        title="[accent]Practice Exercise[/accent]",
        border_style="accent",
        padding=(1, 2),
    ))


def print_code_evaluation(result_content: str) -> None:
    console.print(Panel(
        Markdown(result_content),
        title="[secondary]Code Evaluation[/secondary]",
        border_style="secondary",
        padding=(1, 2),
    ))


def print_assessment_scorecard(score: float, assessment_type: str, feedback: str) -> None:
    passed = score >= 70
    color = "success" if passed else "error"
    status = "PASSED ✔" if passed else "NEEDS REVIEW ✗"

    console.print(Panel(
        Text.from_markup(
            f"[{color}]{status}[/{color}]\n\n"
            f"[white]Score:[/white] [{color}]{score:.1f}%[/{color}]\n"
            f"[white]Type:[/white]  [muted]{assessment_type.replace('_', ' ').title()}[/muted]\n\n"
            f"{feedback}"
        ),
        title="[primary]Assessment Result[/primary]",
        border_style=color,
        padding=(1, 2),
    ))


def stream_token(token: str) -> None:
    """Write a single streaming token to the console without a newline."""
    console.print(token, end="", markup=False, highlight=False)


def stream_end() -> None:
    """Finish a streaming response with a trailing newline."""
    console.print()


def print_error(message: str) -> None:
    console.print(f"[error]Error:[/error] {message}")


def print_info(message: str) -> None:
    console.print(f"[secondary]ℹ[/secondary]  {message}")


def print_success(message: str) -> None:
    console.print(f"[success]✔[/success]  {message}")


def print_thinking_indicator() -> None:
    console.print("[muted]  ⟳  JFST is thinking...[/muted]")


def prompt_input(prompt_text: str = "") -> str:
    display = f"\n[accent]You ▸[/accent] {prompt_text}" if prompt_text else "\n[accent]You ▸[/accent] "
    return console.input(display)


def confirm(message: str) -> bool:
    resp = console.input(f"[warning]{message}[/warning] [muted](yes/no):[/muted] ").strip().lower()
    return resp in ("yes", "y")
