"""Claude-powered lyrics-to-song agent using tool use."""

import json
import anthropic
from music import generate_audio_from_lyrics

CLIENT = anthropic.Anthropic()

SYSTEM_PROMPT = """You are a professional songwriter and music producer.
Your job is to compose original, emotionally resonant song lyrics based on a
description or theme, then immediately call the generate_song tool to produce the audio.

Guidelines for composing lyrics:
- Structure the song clearly with labeled sections: [Verse 1], [Chorus], [Verse 2], [Bridge], etc.
- Tailor the language, imagery, and rhythm to the specified genre
- Make the chorus memorable and repeatable
- Keep verses narrative and personal
- Aim for 3–4 verses and a strong chorus (and optional bridge)

After composing the lyrics in your thinking, call generate_song immediately — do not ask for feedback first."""

TOOLS = [
    {
        "name": "generate_song",
        "description": (
            "Converts composed lyrics into a real MP3 audio file with AI vocals and "
            "genre-appropriate background music. Call this once you have finished composing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "A short, evocative title for the song",
                },
                "lyrics": {
                    "type": "string",
                    "description": "The complete song lyrics with section labels like [Verse 1], [Chorus], etc.",
                },
                "genre": {
                    "type": "string",
                    "description": "The music genre (e.g. pop, rock, hip-hop, jazz, country, r&b, electronic, folk, reggae, classical)",
                },
            },
            "required": ["title", "lyrics", "genre"],
        },
    }
]


def run_agent(description: str, genre: str, output_dir: str = ".") -> dict:
    """Run the agentic loop and return title, lyrics, and audio_path."""
    messages = [
        {
            "role": "user",
            "content": (
                f"Please compose a {genre} song based on this description:\n\n"
                f"{description}\n\n"
                "After composing the lyrics, call generate_song to create the audio file."
            ),
        }
    ]

    result = {"title": None, "lyrics": None, "audio_path": None}

    while True:
        response = CLIENT.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Append the assistant turn to the conversation
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == "generate_song":
                    title = block.input["title"]
                    lyrics = block.input["lyrics"]
                    genre_used = block.input["genre"]

                    result["title"] = title
                    result["lyrics"] = lyrics

                    print(f'\nSong title : "{title}"')
                    print(f"Genre      : {genre_used}")
                    print("\n--- Lyrics ---")
                    print(lyrics)
                    print("--------------")

                    try:
                        audio_path = generate_audio_from_lyrics(
                            lyrics=lyrics,
                            genre=genre_used,
                            title=title,
                            output_dir=output_dir,
                        )
                        result["audio_path"] = audio_path
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Song saved to: {audio_path}",
                            }
                        )
                    except Exception as exc:
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Audio generation failed: {exc}",
                                "is_error": True,
                            }
                        )

            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason — exit loop
            break

    return result
