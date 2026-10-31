import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


VIDEO_SCRIPT = Path(__file__).with_name("text-to-video.py")
SPEC = importlib.util.spec_from_file_location("text_to_video", VIDEO_SCRIPT)
text_to_video = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(text_to_video)


class TextToVideoSyncTests(unittest.TestCase):
    pages = [["first page", "line two"], ["second page"]]

    def test_matching_tts_uses_scene_pages(self):
        chunks = text_to_video.build_tts_chunks("display copy", "display copy", self.pages)

        self.assertEqual(["first page\nline two", "second page"], chunks)

    def test_matching_tts_restores_original_breaks_and_keeps_scenes(self):
        pages = [
            [("Hello world", True), ("this is", False)],
            [("a line", False), ("Next para", True)],
        ]
        chunks = text_to_video.build_tts_chunks("same", "same", pages)

        self.assertEqual(["Hello world this is", "a line\nNext para"], chunks)

    def test_unmatched_tts_stays_as_one_stream(self):
        chunks = text_to_video.build_tts_chunks("alternate speech", "display copy", self.pages)

        self.assertEqual(["alternate speech"], chunks)

    def test_matching_subtitles_use_scene_pages_and_times(self):
        cues = text_to_video.build_subtitle_cues(
            "display copy", "display copy", self.pages, [5.0, 5.0]
        )

        self.assertEqual(
            [(0.0, 5.0, "first page\nline two"), (5.0, 10.0, "second page")],
            cues,
        )

    def test_matching_subtitles_split_into_two_line_cues_weighted_by_text(self):
        pages = [["a", "bb", "ccc", "dddd"]]
        cues = text_to_video.build_subtitle_cues("same", "same", pages, [10.0])

        self.assertEqual(["a\nbb", "ccc\ndddd"], [cue[2] for cue in cues])
        self.assertAlmostEqual(cues[0][0], 0.0)
        self.assertAlmostEqual(cues[0][1], 3.0)
        self.assertAlmostEqual(cues[1][0], 3.0)
        self.assertAlmostEqual(cues[1][1], 10.0)

    def test_unmatched_subtitles_chunk_two_lines_across_total_duration(self):
        cues = text_to_video.build_subtitle_cues(
            "line one\nline two\nline three", "display copy", self.pages, [5.0, 5.0]
        )

        self.assertEqual(
            ["line one\nline two", "line three"],
            [cue[2] for cue in cues],
        )
        self.assertAlmostEqual(cues[0][0], 0.0)
        self.assertAlmostEqual(cues[-1][1], 10.0)

    def test_matching_tts_scene_duration_uses_audio_when_longer(self):
        with patch.object(text_to_video, "audio_duration_seconds", side_effect=[1.0, 4.5]):
            durations = text_to_video.scene_durations_for_tts(2.0, 2, True, ["a", "b"])
        self.assertEqual(durations, [2.0, 4.5])

    def test_audio_duration_falls_back_when_ffprobe_reports_na(self):
        responses = [
            unittest.mock.Mock(stdout="N/A\n"),
            unittest.mock.Mock(stdout="N/A\n"),
            unittest.mock.Mock(stdout="0.000000,0.023220\n1.200000,0.023220\n"),
        ]
        with patch.object(text_to_video.subprocess, "run", side_effect=responses) as run:
            duration = text_to_video.audio_duration_seconds("silent.m4a")
        self.assertAlmostEqual(duration, 1.22322)
        self.assertEqual(run.call_count, 3)

    def test_audio_duration_is_zero_when_ffprobe_has_no_duration(self):
        responses = [
            unittest.mock.Mock(stdout="N/A\n"),
            unittest.mock.Mock(stdout="N/A\n"),
            unittest.mock.Mock(stdout="N/A,N/A\n"),
        ]
        with patch.object(text_to_video.subprocess, "run", side_effect=responses):
            self.assertEqual(0.0, text_to_video.audio_duration_seconds("empty.m4a"))

    def test_matching_subtitles_follow_uneven_scene_durations(self):
        cues = text_to_video.build_subtitle_cues(
            "display copy", "display copy", self.pages, [3.5, 8.25]
        )

        self.assertEqual(
            [(0.0, 3.5, "first page\nline two"), (3.5, 11.75, "second page")],
            cues,
        )

    def test_drawtext_file_replaces_empty_lines_so_ffmpeg_keeps_top_origin(self):
        self.assertEqual(
            " \n**Robert:** Yes.\n \nlast line",
            text_to_video.drawtext_file_text(["", "**Robert:** Yes.", "", "last line"]),
        )

    def test_srt_timestamp_handles_minutes_and_milliseconds(self):
        self.assertEqual("00:01:02,345", text_to_video.format_srt_timestamp(62.345))

    def test_tts_text_argument_loads_file_contents(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
            handle.write("spoken from file")
            path = handle.name
        self.assertEqual("spoken from file", text_to_video.load_text_argument(path))
        self.assertEqual("literal speech", text_to_video.load_text_argument("literal speech"))

    def test_display_text_loads_file_even_with_other_args(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
            handle.write("on screen")
            path = handle.name
        self.assertEqual("on screen", text_to_video.load_display_text([path]))
        self.assertEqual("hello world", text_to_video.load_display_text(["hello", "world"]))

    def test_tts_text_after_display_file_is_not_swallowed(self):
        result = text_to_video.parse_args(
            ["--tts", "janedoe.txt", "--tts-text", "This is alternate audio text."]
        )
        self.assertTrue(result.tts)
        self.assertEqual(["janedoe.txt"], result.text)
        self.assertEqual("This is alternate audio text.", result.tts_text)

    def test_unmatched_tts_keeps_min_scene_time_and_extends_last_if_audio_longer(self):
        with patch.object(text_to_video, "audio_duration_seconds", return_value=1.5):
            self.assertEqual(
                [1.0, 1.0],
                text_to_video.scene_durations_for_tts(1.0, 2, False, ["alt.m4a"]),
            )
        with patch.object(text_to_video, "audio_duration_seconds", return_value=5.0):
            self.assertEqual(
                [1.0, 4.0],
                text_to_video.scene_durations_for_tts(1.0, 2, False, ["alt.m4a"]),
            )


if __name__ == "__main__":
    unittest.main()
