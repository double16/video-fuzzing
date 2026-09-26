#!/usr/bin/env python3

import subprocess
import shlex
import textwrap
import argparse
import tempfile
import os
import sys
import platform

def generate_tts_audio(text):
    """Generate TTS audio and return the temporary filename."""
    system = platform.system()

    if system == "Darwin":
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".m4a")
    elif system == "Linux":
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    else:
        print(f"Unsupported platform for TTS: {system}")
        sys.exit(1)

    temp_audio_path = temp_audio.name
    temp_audio.close()

    try:
        if system == "Darwin":
            subprocess.run(["say", "-o", temp_audio_path, text], check=True)
        elif system == "Linux":
            subprocess.run(["espeak", text, "--stdout"], stdout=open(temp_audio_path, "wb"), check=True)
    except Exception as e:
        print(f"Failed to generate TTS audio: {e}")
        sys.exit(1)

    return temp_audio_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate audio from text"
    )
    parser.add_argument("--output", default="output.mp3", help="Output filename (default: output.mp3)")
    parser.add_argument("text", nargs=argparse.REMAINDER, help="Text to display and/or speak")
    args = parser.parse_args()

    if not args.text:
        parser.error("No text provided.")

    ffmpeg = "ffmpeg"
    # homebrew has extra features we use in ffmpeg-full
    ffmpeg_full = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
    if os.path.exists(ffmpeg_full):
        ffmpeg = ffmpeg_full

    tts_text = ""
    for text_arg in args.text:
        if os.path.exists(text_arg):
            with open(text_arg, "r") as f:
                tts_text += f.read()
        else:
            if tts_text:
                tts_text += " "
            tts_text += text_arg

    if not tts_text:
        parser.error("No text provided.")

    print("Text to audio:", tts_text)

    # -----------------------
    # Setup FFmpeg Inputs
    # -----------------------
    tts_audio_path = generate_tts_audio(tts_text)
    audio_input = f"-i {shlex.quote(tts_audio_path)}"

    # -----------------------
    # Build and Run FFmpeg Command
    # -----------------------
    command = f"""
    {ffmpeg} -y {audio_input} \
    {shlex.quote(args.output)}
    """

    print("Running command:")
    print(command)

    try:
        subprocess.run(command, shell=True, check=True)
    finally:
        os.unlink(tts_audio_path)

if __name__ == "__main__":
    main()

