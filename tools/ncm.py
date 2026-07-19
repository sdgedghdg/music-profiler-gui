"""In-process Netease Cloud Music NCM decryption."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from core.exceptions import NcmDecryptionError

_CORE_KEY = bytes.fromhex("687a4852416d736f356b496e62617857")
_META_KEY = bytes.fromhex("2331346c6a6b5f215c5d2630553c2728")
_MAGIC = b"CTENFDAM"
_MAX_SECTION_SIZE = 64 * 1024 * 1024


@dataclass(frozen=True)
class NcmDecryptResult:
    """The durable audio file and optional metadata extracted from an NCM."""
    file_path: str
    title: str = ""
    artist: str = ""
    album: str = ""


class NcmDecryptor:
    """Decrypt NCM files without an external executable or network access."""

    def decrypt(self, input_path: str | Path, output_dir: str | Path) -> NcmDecryptResult:
        """Decrypt an NCM file into *output_dir* and return its metadata."""
        source = Path(input_path)
        try:
            with source.open("rb") as stream:
                if self._read_exact(stream, len(_MAGIC)) != _MAGIC:
                    raise NcmDecryptionError("Invalid NCM file header")
                self._read_exact(stream, 2)
                key_data = self._read_key_data(stream)
                metadata = self._read_metadata(stream)
                self._read_exact(stream, 5)
                self._skip_cover(stream)
                key_box = self._build_key_box(key_data)
                audio_start = stream.tell()
                header = self._read_audio_header(stream, key_box)
                suffix = self._detect_audio_suffix(header)
                stream.seek(audio_start)
                destination = Path(output_dir) / f"{source.stem}{suffix}"
                self._write_audio(stream, destination, key_box)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, NcmDecryptionError):
                raise
            raise NcmDecryptionError(f"Failed to decrypt NCM file: {exc}") from exc
        return NcmDecryptResult(
            file_path=str(destination),
            title=metadata.get("title", ""),
            artist=metadata.get("artist", ""),
            album=metadata.get("album", ""),
        )

    def _read_key_data(self, stream) -> bytes:
        encrypted = bytes(value ^ 0x64 for value in self._read_section(stream))
        decoded = self._pkcs7_unpad(self._aes_ecb_decrypt(encrypted, _CORE_KEY))
        if len(decoded) <= 17:
            raise NcmDecryptionError("Invalid NCM music key")
        return decoded[17:]

    def _read_metadata(self, stream) -> dict[str, str]:
        encrypted = self._read_section(stream)
        if not encrypted:
            return {}
        try:
            encoded = bytes(value ^ 0x63 for value in encrypted[22:])
            decoded = self._pkcs7_unpad(
                self._aes_ecb_decrypt(base64.b64decode(encoded), _META_KEY)
            ).decode("utf-8")
            _, raw_json = decoded.split(":", 1)
            data = json.loads(raw_json)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NcmDecryptionError(f"Invalid NCM metadata: {exc}") from exc
        if "mainMusic" in data:
            data = data["mainMusic"]
        artists = data.get("artist", [])
        if isinstance(artists, str):
            artist = artists
        elif isinstance(artists, list):
            artist = ", ".join(
                item[0] if isinstance(item, list) and item else item
                for item in artists if isinstance(item, (str, list))
            )
        else:
            artist = ""
        return {
            "title": str(data.get("musicName", "")),
            "artist": artist,
            "album": str(data.get("album", "")),
        }

    def _skip_cover(self, stream) -> None:
        frame_length = self._read_uint32(stream)
        cover_start = stream.tell()
        self._read_section(stream)
        stream.seek(cover_start + frame_length + 4)
        if stream.tell() > self._file_size(stream):
            raise NcmDecryptionError("Invalid NCM cover section")

    def _read_audio_header(self, stream, key_box: bytes) -> bytes:
        encrypted = stream.read(16)
        if not encrypted:
            raise NcmDecryptionError("NCM file has no audio payload")
        return bytes(value ^ key_box[index & 0xff] for index, value in enumerate(encrypted))

    def _write_audio(self, stream, destination: Path, key_box: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        offset = 0
        try:
            with temporary.open("wb") as output:
                while chunk := stream.read(1024 * 1024):
                    output.write(bytes(
                        value ^ key_box[(offset + index) & 0xff]
                        for index, value in enumerate(chunk)
                    ))
                    offset += len(chunk)
            os.replace(temporary, destination)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
        if not data or len(data) % 16:
            raise NcmDecryptionError("Invalid AES block length in NCM file")
        decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
        return decryptor.update(data) + decryptor.finalize()

    @staticmethod
    def _pkcs7_unpad(data: bytes) -> bytes:
        padding = data[-1] if data else 0
        if padding == 0 or padding > 16 or data[-padding:] != bytes([padding]) * padding:
            raise NcmDecryptionError("Invalid NCM padding")
        return data[:-padding]

    @staticmethod
    def _build_key_box(key: bytes) -> bytes:
        if not key:
            raise NcmDecryptionError("NCM music key is empty")
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

    def _read_section(self, stream) -> bytes:
        length = self._read_uint32(stream)
        if length > _MAX_SECTION_SIZE:
            raise NcmDecryptionError("NCM section exceeds size limit")
        return self._read_exact(stream, length)

    @staticmethod
    def _read_uint32(stream) -> int:
        return int.from_bytes(NcmDecryptor._read_exact(stream, 4), "little")

    @staticmethod
    def _read_exact(stream, length: int) -> bytes:
        data = stream.read(length)
        if len(data) != length:
            raise NcmDecryptionError("Unexpected end of NCM file")
        return data

    @staticmethod
    def _file_size(stream) -> int:
        position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(position)
        return size

    @staticmethod
    def _detect_audio_suffix(header: bytes) -> str:
        if header.startswith(b"fLaC"):
            return ".flac"
        if header.startswith(b"OggS"):
            return ".ogg"
        if header.startswith(b"ID3") or header[:1] == b"\xff":
            return ".mp3"
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return ".m4a"
        raise NcmDecryptionError("Could not identify decrypted NCM audio format")
