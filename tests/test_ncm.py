"""Tests for in-process NCM decryption."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from core.exceptions import NcmDecryptionError
from tools.ncm import NcmDecryptor

_CORE_KEY = bytes.fromhex("687a4852416d736f356b496e62617857")
_META_KEY = bytes.fromhex("2331346c6a6b5f215c5d2630553c2728")


def _pad(data: bytes) -> bytes:
    size = 16 - len(data) % 16
    return data + bytes([size]) * size


def _encrypt(data: bytes, key: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(_pad(data)) + encryptor.finalize()


def _key_box(key: bytes) -> bytes:
    box = list(range(256))
    index = 0
    for value in range(256):
        index = (box[value] + index + key[value % len(key)]) & 0xff
        box[value], box[index] = box[index], box[value]
    result = []
    for value in range(256):
        next_index = (value + 1) & 0xff
        first = box[next_index]
        second = box[(next_index + first) & 0xff]
        result.append(box[(first + second) & 0xff])
    return bytes(result)


def _make_ncm(path: Path, audio: bytes) -> None:
    key = b"test-ncm-key"
    key_section = bytes(value ^ 0x64 for value in _encrypt(b"neteasecloudmusic" + key, _CORE_KEY))
    metadata = {
        "musicName": "Native Test",
        "artist": [["Artist", 1]],
        "album": "Album",
    }
    raw_metadata = b"music:" + json.dumps(metadata).encode()
    encoded_metadata = b"163 key(Don't modify):" + base64.b64encode(
        _encrypt(raw_metadata, _META_KEY)
    )
    meta_section = bytes(value ^ 0x63 for value in encoded_metadata)
    box = _key_box(key)
    encrypted_audio = bytes(
        value ^ box[index & 0xff] for index, value in enumerate(audio)
    )
    path.write_bytes(
        b"CTENFDAM" + b"\x00\x00" +
        len(key_section).to_bytes(4, "little") + key_section +
        len(meta_section).to_bytes(4, "little") + meta_section +
        b"\x00" * 5 +
        (0).to_bytes(4, "little") + (0).to_bytes(4, "little") +
        encrypted_audio
    )


def test_decrypt_ncm_writes_original_audio_and_metadata(tmp_path):
    source = tmp_path / "song.ncm"
    audio = b"ID3" + b"\x00" * 64
    _make_ncm(source, audio)

    result = NcmDecryptor().decrypt(source, tmp_path / "output")

    assert Path(result.file_path).read_bytes() == audio
    assert Path(result.file_path).suffix == ".mp3"
    assert result.title == "Native Test"
    assert result.artist == "Artist"
    assert result.album == "Album"


def test_decrypt_rejects_invalid_header(tmp_path):
    source = tmp_path / "broken.ncm"
    source.write_bytes(b"not an ncm")

    with pytest.raises(NcmDecryptionError, match="header"):
        NcmDecryptor().decrypt(source, tmp_path / "output")


def test_decrypt_rejects_truncated_ncm(tmp_path):
    source = tmp_path / "broken.ncm"
    source.write_bytes(b"CTENFDAM\x00\x00\x10\x00\x00\x00")

    with pytest.raises(NcmDecryptionError, match="Unexpected end"):
        NcmDecryptor().decrypt(source, tmp_path / "output")
