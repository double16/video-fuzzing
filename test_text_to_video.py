import importlib.util
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

    def test_unmatched_subtitles_repeat_full_text_in_equal_time_cues(self):
        cues = text_to_video.build_subtitle_cues(
            "alternate subtitle", "display copy", self.pages, [5.0, 5.0]
        )

        self.assertEqual(
            [(0.0, 5.0, "alternate subtitle"), (5.0, 10.0, "alternate subtitle")],
            cues,
        )

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

    def test_srt_timestamp_handles_minutes_and_milliseconds(self):
        self.assertEqual("00:01:02,345", text_to_video.format_srt_timestamp(62.345))


if __name__ == "__main__":
    unittest.main()
