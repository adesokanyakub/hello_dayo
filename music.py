"""Music generation using Replicate (Bark for vocals, MusicGen for background)."""

import os
import re
import tempfile
from pathlib import Path

import replicate
import requests
from pydub import AudioSegment

# Maps genre to a Bark voice preset that fits the style
GENRE_VOICE_MAP = {
    "pop": "en_speaker_6",
    "rock": "en_speaker_9",
    "hip-hop": "en_speaker_5",
    "jazz": "en_speaker_3",
    "country": "en_speaker_7",
    "r&b": "en_speaker_4",
    "electronic": "en_speaker_2",
    "folk": "en_speaker_0",
    "reggae": "en_speaker_1",
    "classical": "en_speaker_8",
}

# Maps genre to a MusicGen prompt for the backing track
GENRE_MUSIC_PROMPTS = {
    "pop": "upbeat pop instrumental, catchy melody, modern production, synthesizers, drums, bass",
    "rock": "rock instrumental, electric guitar, drums, bass, powerful riffs, no vocals",
    "hip-hop": "hip-hop beat, 808 bass, trap drums, rap instrumental, urban, no vocals",
    "jazz": "smooth jazz instrumental, piano, saxophone, double bass, brushed drums",
    "country": "country instrumental, acoustic guitar, fiddle, steel guitar, Nashville sound",
    "r&b": "R&B soul instrumental, smooth groove, bass guitar, piano, neo-soul",
    "electronic": "electronic dance instrumental, synthesizers, EDM, four-on-the-floor beat",
    "folk": "folk instrumental, acoustic guitar, gentle strumming, warm and intimate",
    "reggae": "reggae instrumental, offbeat guitar, bass, drums, Caribbean rhythm",
    "classical": "orchestral instrumental, strings, piano, classical composition, majestic",
}

# Replicate model identifiers
BARK_MODEL = "suno-ai/bark:b76242b40d67c76ab6742e987628a2a9ac019e11d56ab96c4e91ce03b79b2787"
MUSICGEN_MODEL = "meta/musicgen:671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"


def generate_audio_from_lyrics(lyrics: str, genre: str, title: str, output_dir: str = ".") -> str:
    """Generate a complete song MP3 by combining AI vocals and background music.

    Returns the path to the saved MP3 file.
    """
    genre_key = genre.lower().replace(" ", "-")
    voice_preset = GENRE_VOICE_MAP.get(genre_key, "en_speaker_6")
    music_prompt = GENRE_MUSIC_PROMPTS.get(genre_key, f"{genre} instrumental, professional production, no vocals")

    safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
    output_path = str(Path(output_dir) / f"{safe_title}.mp3")

    with tempfile.TemporaryDirectory() as tmpdir:
        print("  [1/3] Generating vocals from lyrics...")
        vocal_path = _generate_vocals(lyrics, voice_preset, tmpdir)

        print("  [2/3] Generating background music...")
        music_path = _generate_background_music(music_prompt, tmpdir)

        print("  [3/3] Mixing tracks and exporting MP3...")
        _mix_and_export(vocal_path, music_path, output_path)

    return output_path


def _generate_vocals(lyrics: str, voice_preset: str, tmpdir: str) -> str:
    """Use Bark to convert lyrics into sung/spoken audio."""
    musical_prompt = _format_lyrics_for_bark(lyrics)

    output = replicate.run(
        BARK_MODEL,
        input={
            "prompt": musical_prompt,
            "history_prompt": voice_preset,
        },
    )

    vocal_path = os.path.join(tmpdir, "vocals.wav")
    _download_to_file(_resolve_url(output), vocal_path)
    return vocal_path


def _generate_background_music(prompt: str, tmpdir: str) -> str:
    """Use MusicGen to create a genre-appropriate instrumental backing track."""
    output = replicate.run(
        MUSICGEN_MODEL,
        input={
            "prompt": prompt,
            "duration": 30,
            "model_version": "stereo-large",
            "output_format": "mp3",
            "normalization_strategy": "loudness",
        },
    )

    music_path = os.path.join(tmpdir, "background.mp3")
    _download_to_file(_resolve_url(output), music_path)
    return music_path


def _mix_and_export(vocal_path: str, music_path: str, output_path: str) -> None:
    """Overlay vocals on the background track and export as MP3."""
    vocals = AudioSegment.from_file(vocal_path)
    background = AudioSegment.from_file(music_path)

    # Lower background by 12 dB so vocals are clearly audible
    background = background - 12

    # Loop or trim background to match vocal length
    if len(background) < len(vocals):
        repeats = (len(vocals) // len(background)) + 1
        background = background * repeats
    background = background[: len(vocals)]

    mixed = background.overlay(vocals)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    mixed.export(output_path, format="mp3", bitrate="192k")


def _format_lyrics_for_bark(lyrics: str) -> str:
    """Strip section headers and wrap each lyric line with musical notation."""
    lines = []
    for line in lyrics.strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("["):
            continue
        lines.append(f"♪ {stripped} ♪")  # ♪ line ♪
    # Bark handles ~15–20 lines well; truncate to avoid timeouts
    return "\n".join(lines[:18])


def _resolve_url(output) -> str:
    """Normalise a Replicate output to a plain URL string."""
    if isinstance(output, str):
        return output
    if hasattr(output, "url"):
        return output.url
    # FileOutput objects support str() in newer SDK versions
    return str(output)


def _download_to_file(url: str, dest: str) -> None:
    """Stream a URL response to a local file."""
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in response.iter_content(chunk_size=8192):
            fh.write(chunk)
