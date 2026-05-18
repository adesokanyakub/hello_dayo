#!/usr/bin/env python3
"""Lyrics-to-Song Agent CLI.

Compose AI lyrics and generate a genre-specific MP3 from a description.

Usage:
    python main.py
    python main.py --description "..." --genre pop --output-dir ./songs
"""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

GENRES = [
    "pop",
    "rock",
    "hip-hop",
    "jazz",
    "country",
    "r&b",
    "electronic",
    "folk",
    "reggae",
    "classical",
]


def _check_env() -> None:
    missing = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not os.environ.get("REPLICATE_API_TOKEN"):
        missing.append("REPLICATE_API_TOKEN")
    if missing:
        click.echo(
            f"Error: missing environment variable(s): {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in your API keys.",
            err=True,
        )
        sys.exit(1)


@click.command()
@click.option(
    "--description",
    "-d",
    default=None,
    help="Description or theme for the song.",
)
@click.option(
    "--genre",
    "-g",
    type=click.Choice(GENRES, case_sensitive=False),
    default=None,
    help=f"Music genre. Choices: {', '.join(GENRES)}",
)
@click.option(
    "--output-dir",
    "-o",
    default="./output",
    show_default=True,
    help="Directory to save the generated MP3.",
)
def main(description: str, genre: str, output_dir: str) -> None:
    """Generate a song from a text description using AI.

    If --description or --genre are omitted you will be prompted interactively.
    """
    _check_env()

    # Lazy import so env check runs first
    from agent import run_agent  # noqa: PLC0415

    if not description:
        description = click.prompt("Describe your song (theme, mood, story, etc.)")

    if not genre:
        click.echo(f"\nAvailable genres: {', '.join(GENRES)}")
        genre = click.prompt(
            "Select a genre",
            type=click.Choice(GENRES, case_sensitive=False),
        )

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    click.echo(f"\nCreating a {genre} song about: {description}")
    click.echo("Composing lyrics with Claude...\n")

    result = run_agent(description=description, genre=genre, output_dir=output_dir)

    if result.get("audio_path"):
        click.echo(f"\nDone! MP3 saved to: {result['audio_path']}")
    else:
        click.echo("\nAgent finished but no audio file was produced.", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
