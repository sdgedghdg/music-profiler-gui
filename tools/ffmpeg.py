"""FFmpeg wrapper for transcoding, concatenation, loudness normalisation, and stem merging."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from core.exceptions import ToolExecutionError
from core.models import ProcessConfig
from tools.base import ToolRunner, require_runner

logger = logging.getLogger(__name__)

_CODEC_MAP = {
    "mp3": "libmp3lame",
    "aac": "aac",
    "flac": "flac",
    "wav": "pcm_s16le",
    "ogg": "libvorbis",
    "opus": "libopus",
}

#: FLAC rejects frames longer than 1024 samples for the default block size; the
#: hard ceiling is 65535.  ``loudnorm`` resamples to 192 kHz, which makes a
#: multi-second frame far larger, so force a legal block size for FLAC output.
_FLAC_MAX_BLOCK_SIZE = 4096


def _parse_loudnorm_json(stderr: str) -> dict:
    """Extract the loudnorm measurement JSON from ffmpeg stderr."""
    required = {
        "input_i", "input_tp", "input_lra", "input_thresh", "target_offset",
    }
    decoder = json.JSONDecoder()
    start = 0
    while True:
        index = stderr.find("{", start)
        if index == -1:
            break
        try:
            parsed, length = decoder.raw_decode(stderr[index:])
        except json.JSONDecodeError:
            start = index + 1
            continue
        if isinstance(parsed, dict) and required.issubset(parsed):
            return parsed
        start = index + max(length, 1)
    raise ToolExecutionError(
        "Failed to parse loudnorm analysis: measurement JSON was not found"
    )


class FFmpeg:
    """Wrapper around ffmpeg for audio processing operations."""

    def __init__(self, runner: ToolRunner | None = None) -> None:
        self._runner = runner

    def transcode(
        self, input_path: str | Path, output_path: str | Path, config: ProcessConfig
    ) -> None:
        """Convert *input_path* to *output_path* using *config*."""
        runner = require_runner(self._runner)
        input_path = Path(input_path)
        output_path = Path(output_path)
        args: list[str] = [
            "-y", "-i", str(input_path), "-map", "0:a:0", "-vn",
        ]

        codec = _CODEC_MAP.get(config.output_format)
        if codec:
            args.extend(["-c:a", codec])
        if config.sample_rate_hz:
            args.extend(["-ar", str(config.sample_rate_hz)])
        if config.bitrate_bps:
            args.extend(["-b:a", str(config.bitrate_bps)])
        if config.channels:
            args.extend(["-ac", str(config.channels)])
        if config.target_loudness_lufs is not None:
            filters = [f"loudnorm=I={config.target_loudness_lufs}:TP=-1.5:LRA=11"]
            if config.sample_rate_hz:
                # loudnorm upsamples to 192 kHz internally; pin the output rate
                # back to the requested rate so the result matches -ar.
                filters.append(f"aresample={config.sample_rate_hz}")
            if config.output_format == "flac":
                # FLAC rejects frames longer than 65535 samples, which loudnorm's
                # 192 kHz upsample can exceed.  Force a legal frame size.
                filters.append(f"asetnsamples=n={_FLAC_MAX_BLOCK_SIZE}:p=0")
            args.extend(["-af", ",".join(filters)])

        args.append(str(output_path))
        logger.info("Transcoding: %s -> %s", input_path, output_path)
        runner.run(args)

    def concat(
        self,
        input_paths: list[str],
        output_path: str,
        format: str = "mp3",  # noqa: A002
    ) -> None:
        """Concatenate audio files using the concat demuxer."""
        runner = require_runner(self._runner)
        if not input_paths:
            raise ToolExecutionError("No input paths provided for concat")

        fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="musprof_concat_")
        try:
            with os.fdopen(fd, "w") as fh:
                for p in input_paths:
                    fh.write(f"file '{p}'\n")

            codec = _CODEC_MAP.get(format, "copy")
            args = [
                "-y", "-f", "concat", "-safe", "0",
                "-i", tmp_path, "-c:a", codec, str(output_path),
            ]
            logger.info(
                "Concatenating %d files into %s", len(input_paths), output_path
            )
            runner.run(args)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning("Failed to clean up temp concat file: %s", tmp_path)

    def normalize_loudness(
        self,
        input_path: str | Path,
        output_path: str | Path,
        target_lufs: float = -16.0,
    ) -> None:
        """Two-pass EBU R128 loudness normalisation."""
        runner = require_runner(self._runner)
        input_path = Path(input_path)
        output_path = Path(output_path)

        # Pass 1: analyse
        pass1_args = [
            "-y", "-i", str(input_path),
            "-af",
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "-",
        ]
        logger.info("Loudnorm pass 1 (analyse): %s", input_path)
        stats = _parse_loudnorm_json(runner.run(pass1_args).stderr)

        # Pass 2: apply
        loudnorm_filter = (
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
            f":measured_I={stats['input_i']}"
            f":measured_TP={stats['input_tp']}"
            f":measured_LRA={stats['input_lra']}"
            f":measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}"
            ":linear=true:print_format=summary"
        )
        if output_path.suffix.lower() == ".flac":
            # loudnorm resamples to 192 kHz; FLAC caps frames at 65535 samples.
            loudnorm_filter += f",asetnsamples=n={_FLAC_MAX_BLOCK_SIZE}:p=0"
        pass2_args = [
            "-y", "-i", str(input_path), "-af", loudnorm_filter, str(output_path),
        ]
        logger.info(
            "Loudnorm pass 2 (apply): %s -> %s", input_path, output_path
        )
        runner.run(pass2_args)

    def merge_stems(
        self, stem_paths: list[str], output_path: str
    ) -> None:
        """Mix multiple audio stems into a single stereo track via amix."""
        runner = require_runner(self._runner)
        if not stem_paths:
            raise ToolExecutionError("No stem paths provided for merge")

        inputs: list[str] = []
        for p in stem_paths:
            inputs.extend(["-i", str(p)])

        amix = f"amix=inputs={len(stem_paths)}:duration=longest:normalize=0"
        args = ["-y"] + inputs + ["-filter_complex", amix, str(output_path)]

        logger.info("Merging %d stems into %s", len(stem_paths), output_path)
        runner.run(args)
