"""Tests for FFmpeg loudnorm result parsing."""

from __future__ import annotations

import pytest

from core.exceptions import ToolExecutionError
from tools.ffmpeg import _parse_loudnorm_json


def test_parse_loudnorm_skips_unrelated_json():
    stderr = '''
    [info] {"input_file":"song.mp3"}
    [Parsed_loudnorm] {
        "input_i" : "-15.20",
        "input_tp" : "-0.10",
        "input_lra" : "5.10",
        "input_thresh" : "-25.20",
        "target_offset" : "0.08"
    }
    '''

    stats = _parse_loudnorm_json(stderr)

    assert stats["input_i"] == "-15.20"



def test_parse_loudnorm_rejects_non_measurement_json():
    with pytest.raises(ToolExecutionError, match="measurement JSON"):
        _parse_loudnorm_json('{"input_file":"song.mp3"}')


def test_transcode_maps_only_the_first_audio_stream(tmp_path):
    from unittest.mock import MagicMock

    from core.models import ProcessConfig
    from tools.base import ToolRunner
    from tools.ffmpeg import FFmpeg

    runner = MagicMock(spec=ToolRunner)
    source = tmp_path / "source.mp3"
    output = tmp_path / "output.mp3"
    FFmpeg(runner).transcode(source, output, ProcessConfig())

    args = runner.run.call_args.args[0]
    assert ["-map", "0:a:0", "-vn"] == args[3:6]
