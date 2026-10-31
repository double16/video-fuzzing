#!/usr/bin/env python3

import subprocess
import shlex
import argparse
import tempfile
import os
import sys
import platform
from text_layout import canvas_size, content_height, paginate_lines, speech_text_for_units, wrap_units

def generate_tts_audio(text):
    """Generate TTS audio and return the temporary filename."""
    system = platform.system()
    audio_suffix = ".m4a"

    if system == "Linux":
        audio_suffix = ".wav"
    elif system != "Darwin":
        print(f"Unsupported platform for TTS: {system}")
        sys.exit(1)

    temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=audio_suffix)
    temp_audio_path = temp_audio.name
    temp_audio.close()

    try:
        if system == "Darwin":
            subprocess.run(["say", "-o", temp_audio_path, text], check=True)
        elif system == "Linux":
            with open(temp_audio_path, "wb") as audio_file:
                subprocess.run(["espeak", text, "--stdout"], stdout=audio_file, check=True)
    except Exception as e:
        print(f"Failed to generate TTS audio: {e}")
        os.unlink(temp_audio_path)
        sys.exit(1)

    return temp_audio_path

def format_srt_timestamp(seconds):
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def page_display_lines(page):
    if page and isinstance(page[0], tuple):
        return [line for line, _starts_original in page]
    return list(page)


def drawtext_file_text(page_lines):
    # FFmpeg drawtext treats a leading empty line as a bottom-aligned origin,
    # which clips all but the last lines off the top of the frame.
    return "\n".join(line if line else " " for line in page_lines)


def build_tts_chunks(tts_text, display_text, pages):
    if tts_text == display_text:
        return [
            speech_text_for_units(page) if page and isinstance(page[0], tuple) else "\n".join(page)
            for page in pages
        ]
    return [tts_text]


def _ffprobe_duration(audio_path, entries):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", entries,
            "-of", "default=noprint_wrappers=1:nokey=1", audio_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        value = line.strip()
        if not value or value.upper() == "N/A":
            continue
        try:
            duration = float(value)
        except ValueError:
            continue
        if duration > 0:
            return duration
    return None


def audio_duration_seconds(audio_path):
    duration = _ffprobe_duration(audio_path, "format=duration")
    if duration is None:
        duration = _ffprobe_duration(audio_path, "stream=duration")
    if duration is None:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "packet=pts_time,duration_time",
                "-of", "csv=p=0", audio_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        last_end = 0.0
        for line in result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 1:
                continue
            try:
                pts = float(parts[0]) if parts[0] and parts[0].upper() != "N/A" else 0.0
                packet_duration = float(parts[1]) if len(parts) > 1 and parts[1] and parts[1].upper() != "N/A" else 0.0
            except ValueError:
                continue
            last_end = max(last_end, pts + packet_duration)
        duration = last_end if last_end > 0 else None
    if duration is None:
        return 0.0
    return duration


def scene_durations_for_tts(min_scene_duration, scene_count, tts_matches_display, audio_paths):
    if tts_matches_display and audio_paths:
        return [
            max(min_scene_duration, audio_duration_seconds(audio_path))
            for audio_path in audio_paths
        ]
    durations = [min_scene_duration] * scene_count
    if audio_paths:
        extra = audio_duration_seconds(audio_paths[0]) - sum(durations)
        if extra > 0:
            durations[-1] += extra
    return durations


MAX_SUBTITLE_LINES = 2


def chunk_lines(lines, max_lines=MAX_SUBTITLE_LINES):
    lines = list(lines) or [""]
    return [lines[index:index + max_lines] for index in range(0, len(lines), max_lines)]


def _cue_weight(text):
    return max(1, len(text.replace("\n", "")))


def _cues_for_chunks(chunks, start, duration):
    weights = [_cue_weight("\n".join(chunk)) for chunk in chunks]
    total_weight = sum(weights)
    cues = []
    offset = start
    remaining = duration
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        if index == len(chunks) - 1:
            chunk_duration = remaining
        else:
            chunk_duration = duration * (weight / total_weight)
            remaining -= chunk_duration
        end = offset + chunk_duration
        cues.append((offset, end, "\n".join(chunk)))
        offset = end
    return cues


def build_subtitle_cues(subtitle_text, display_text, pages, scene_durations):
    cues = []
    start = 0.0
    if subtitle_text == display_text:
        for page, scene_duration in zip(pages, scene_durations):
            chunks = chunk_lines(page_display_lines(page))
            cues.extend(_cues_for_chunks(chunks, start, scene_duration))
            start += scene_duration
        return cues

    unmatched_lines = subtitle_text.splitlines() or [subtitle_text]
    chunks = chunk_lines(unmatched_lines)
    total_duration = sum(scene_durations)
    return _cues_for_chunks(chunks, 0.0, total_duration)


def generate_srt(cues):
    """Generate an SRT file from timed subtitle cues."""
    temp_sub = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="w", encoding="utf-8")
    temp_sub_path = temp_sub.name
    for cue_index, (start_seconds, end_seconds, text) in enumerate(cues, start=1):
        temp_sub.write(
            f"{cue_index}\n{format_srt_timestamp(start_seconds)} --> "
            f"{format_srt_timestamp(end_seconds)}\n{text}\n\n"
        )
    temp_sub.close()
    return temp_sub_path


def concat_quote(path):
    return "'" + os.path.abspath(path).replace("'", "'\\''") + "'"


def load_text_argument(value):
    if value and os.path.isfile(value):
        with open(value, encoding="utf-8") as text_file:
            return text_file.read()
    return value


def load_display_text(text_args):
    if len(text_args) == 1 and os.path.isfile(text_args[0]):
        return load_text_argument(text_args[0])
    display_text = ""
    for text_arg in text_args:
        if os.path.isfile(text_arg):
            display_text += load_text_argument(text_arg)
        else:
            if display_text:
                display_text += " "
            display_text += text_arg
    return display_text


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Generate a video with text, optional Text-to-Speech, and optional embedded subtitles."
    )
    parser.add_argument("--fontsize", type=int, default=32, help="Font size in pixels (default: 32 pixels)")
    parser.add_argument("--duration", type=int, default=10, help="Duration of the video in seconds (default: 10)")
    parser.add_argument("--output", default="output.mp4", help="Output filename (default: output.mp4)")
    parser.add_argument("--fontcolor", default="white", help="Font color (default: white)")
    parser.add_argument("--background", default="black", help="Background color (default: black)")
    parser.add_argument("--maxwidth", type=int, default=1280, help="Maximum video width in pixels (default: 1280)")
    parser.add_argument("--maxheight", type=int, default=720, help="Maximum video height in pixels (default: 720)")
    parser.add_argument("--volume", type=float, default=-30, help="White noise volume in decibels (dB) (default: -30)")
    parser.add_argument("--margin", type=int, default=10, help="Margin around the text in pixels (default: 10)")
    parser.add_argument("--tts", action="store_true", help="Use TTS audio instead of white noise")
    parser.add_argument("--tts-text", help="Alternate text to use for TTS (default: same as visible text)")
    parser.add_argument("--subtitle-text", help="Alternate text to use for subtitles (default: same as TTS text, which defaults to visible text)")
    parser.add_argument("--subtitle-language", default="eng", help="Subtitle language ISO 639-2 code (default: eng)")
    parser.add_argument("text", nargs="*", help="Text or a UTF-8 text file path to display and/or speak")
    return parser


def parse_args(argv=None):
    return build_arg_parser().parse_args(argv)


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.text:
        parser.error("No text provided.")
    if args.duration <= 0:
        parser.error("--duration must be greater than zero.")

    ffmpeg = "ffmpeg"
    # homebrew has extra features we use in ffmpeg-full
    ffmpeg_full = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
    if os.path.exists(ffmpeg_full):
        ffmpeg = ffmpeg_full

    display_text = load_display_text(args.text)
    tts_text = load_text_argument(args.tts_text) if args.tts_text else display_text
    subtitle_text = load_text_argument(args.subtitle_text) if args.subtitle_text else tts_text

    pages = paginate_lines(
        wrap_units(display_text, args.fontsize, args.maxwidth, args.margin),
        args.fontsize,
        args.maxheight,
        args.margin,
    )
    char_pixel_width = max(1, args.fontsize * 0.6)
    min_scene_duration = args.duration / len(pages)
    tts_audio_paths = []
    subtitle_path = None
    tts_matches_display = tts_text == display_text

    try:
        if args.tts:
            for tts_chunk in build_tts_chunks(tts_text, display_text, pages):
                tts_audio_paths.append(generate_tts_audio(tts_chunk))
        scene_durations = scene_durations_for_tts(
            min_scene_duration, len(pages), args.tts and tts_matches_display, tts_audio_paths
        )
        total_duration = sum(scene_durations)

        with tempfile.TemporaryDirectory(prefix="text-to-video-") as temp_dir:
            scene_paths = []
            longest_line_length = max(len(line) for page in pages for line in page_display_lines(page))
            max_lines_per_scene = max(len(page) for page in pages)
            width, height = canvas_size(
                min(args.maxwidth, int(longest_line_length * char_pixel_width) + args.margin * 2),
                min(args.maxheight, content_height(max_lines_per_scene, args.fontsize, args.margin)),
            )
            print(f"Calculated video size: {width}x{height}")

            for scene_index, page in enumerate(pages):
                page_lines = page_display_lines(page)
                scene_duration = scene_durations[scene_index]
                print(f"Scene {scene_index + 1}/{len(pages)}: {width}x{height} ({scene_duration:.3f}s)")
                print("Text lines:")
                print("\n".join(page_lines))

                drawtext_path = os.path.join(temp_dir, f"scene_{scene_index + 1:03}.txt")
                with open(drawtext_path, "w", encoding="utf-8") as drawtext_file:
                    drawtext_file.write(drawtext_file_text(page_lines))
                escaped_drawtext_path = (
                    drawtext_path.replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")
                )
                drawtext_filter = (
                    f"drawtext=textfile='{escaped_drawtext_path}':expansion=none:"
                    f"font='Courier New Bold':fontcolor={args.fontcolor}:fontsize={args.fontsize}:"
                    f"x={args.margin}:y={args.margin}:line_spacing={max(0, int(args.fontsize * 0.5))}"
                )
                scene_paths.append(os.path.join(temp_dir, f"scene_{scene_index + 1:03}.mp4"))
                command = [
                    ffmpeg, "-y", "-f", "lavfi", "-i",
                    f"color=c={args.background}:s={width}x{height}:d={scene_duration:.6f}",
                ]
                command.extend([
                    "-filter_complex", f"[0:v]{drawtext_filter}[v]",
                    "-map", "[v]", "-an",
                    "-t", f"{scene_duration:.6f}",
                    "-c:v", "libx264", "-crf:v", "20",
                    scene_paths[-1],
                ])
                print("Running command:")
                print(shlex.join(command))
                subprocess.run(command, check=True)

            concat_path = os.path.join(temp_dir, "concat.txt")
            joined_video_path = os.path.join(temp_dir, "joined-video.mp4")
            with open(concat_path, "w", encoding="utf-8") as concat_file:
                for scene_path in scene_paths:
                    concat_file.write(f"file {concat_quote(scene_path)}\n")
            concat_command = [
                ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_path,
                "-c", "copy", joined_video_path,
            ]
            print("Running concat command:")
            print(shlex.join(concat_command))
            subprocess.run(concat_command, check=True)

            mux_command = [ffmpeg, "-y", "-i", joined_video_path]
            audio_filters = []
            if args.tts:
                for audio_path in tts_audio_paths:
                    mux_command.extend(["-i", audio_path])
                if tts_matches_display:
                    for scene_index, scene_duration in enumerate(scene_durations):
                        audio_input_index = scene_index + 1
                        audio_filters.append(
                            f"[{audio_input_index}:a:0]aresample=44100,"
                            "aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
                            f"atrim=duration={scene_duration:.6f},asetpts=PTS-STARTPTS[a{scene_index}]"
                        )
                    audio_inputs = "".join(f"[a{index}]" for index in range(len(pages)))
                    audio_filters.append(f"{audio_inputs}concat=n={len(pages)}:v=0:a=1[a]")
                else:
                    audio_filters.append(
                        "[1:a:0]aresample=44100,"
                        "aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
                        f"atrim=duration={total_duration:.6f},asetpts=PTS-STARTPTS[a]"
                    )
                audio_input_count = len(tts_audio_paths)
            else:
                mux_command.extend([
                    "-f", "lavfi", "-i",
                    f"anoisesrc=color=white:duration={total_duration}:sample_rate=44100",
                ])
                audio_filters.append(
                    f"[1:a]volume={args.volume}dB,atrim=duration={total_duration},"
                    "asetpts=PTS-STARTPTS[a]"
                )
                audio_input_count = 1

            subtitle_path = generate_srt(
                build_subtitle_cues(subtitle_text, display_text, pages, scene_durations)
            )
            mux_command.extend(["-f", "srt", "-i", subtitle_path])
            subtitle_input_index = 1 + audio_input_count
            audio_map = "[a]"
            mux_command.extend([
                "-filter_complex", ";".join(audio_filters),
                "-map", "0:v:0", "-map", audio_map, "-map", f"{subtitle_input_index}:s:0",
                "-t", f"{total_duration:.6f}",
                "-c:v", "copy", "-c:a", "aac", "-c:s", "mov_text",
                "-metadata:s:s:0", f"language={args.subtitle_language}",
                "-movflags", "+faststart", args.output,
            ])
            print("Running mux command:")
            print(shlex.join(mux_command))
            subprocess.run(mux_command, check=True)
    finally:
        for tts_audio_path in tts_audio_paths:
            os.unlink(tts_audio_path)
        if subtitle_path:
            os.unlink(subtitle_path)

if __name__ == "__main__":
    main()
