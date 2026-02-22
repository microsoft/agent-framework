# Copyright (c) Microsoft. All rights reserved.

"""Audio utilities for encoding, decoding, and file I/O."""

import base64
import wave
from typing import BinaryIO


class AudioUtils:
    """Utilities for audio encoding/decoding and file I/O."""

    @staticmethod
    def encode_pcm16_to_base64(audio_bytes: bytes) -> str:
        """Encode PCM16 audio bytes to base64 string.

        Args:
            audio_bytes: Raw PCM16 audio bytes

        Returns:
            Base64-encoded string
        """
        return base64.b64encode(audio_bytes).decode("utf-8")

    @staticmethod
    def decode_base64_to_pcm16(audio_b64: str) -> bytes:
        """Decode base64 string to PCM16 audio bytes.

        Args:
            audio_b64: Base64-encoded audio string

        Returns:
            Raw PCM16 audio bytes
        """
        return base64.b64decode(audio_b64)

    @staticmethod
    def save_to_wav(
        audio_bytes: bytes, file_path: str, sample_rate: int = 24000, channels: int = 1
    ) -> None:
        """Save PCM16 audio to WAV file.

        Args:
            audio_bytes: Raw PCM16 audio bytes
            file_path: Path to output WAV file
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels (1=mono, 2=stereo)
        """
        with wave.open(file_path, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)  # 2 bytes for PCM16
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_bytes)

    @staticmethod
    def load_from_wav(file_path: str) -> tuple[bytes, int, int]:
        """Load PCM16 audio from WAV file.

        Args:
            file_path: Path to input WAV file

        Returns:
            Tuple of (audio_bytes, sample_rate, channels)

        Raises:
            ValueError: If WAV file is not PCM16 format
        """
        with wave.open(file_path, "rb") as wav_file:
            # Validate format
            if wav_file.getsampwidth() != 2:
                raise ValueError(f"WAV file must be PCM16 (16-bit), got {wav_file.getsampwidth() * 8}-bit")

            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            audio_bytes = wav_file.readframes(wav_file.getnframes())

            return audio_bytes, sample_rate, channels

    @staticmethod
    def resample_audio(
        audio_bytes: bytes,
        from_sample_rate: int,
        to_sample_rate: int,
        channels: int = 1,
    ) -> bytes:
        """Resample PCM16 audio to a different sample rate.

        Note: This is a simple nearest-neighbor resampling. For production use,
        consider using a library like scipy or librosa for higher quality resampling.

        Args:
            audio_bytes: Raw PCM16 audio bytes
            from_sample_rate: Source sample rate in Hz
            to_sample_rate: Target sample rate in Hz
            channels: Number of audio channels

        Returns:
            Resampled PCM16 audio bytes
        """
        if from_sample_rate == to_sample_rate:
            return audio_bytes

        import struct

        # Convert bytes to samples
        sample_format = "<h"  # Little-endian signed 16-bit integer
        bytes_per_sample = channels * 2
        num_samples = len(audio_bytes) // bytes_per_sample

        samples = []
        for i in range(num_samples):
            offset = i * bytes_per_sample
            if channels == 1:
                sample = struct.unpack(sample_format, audio_bytes[offset : offset + 2])[0]
                samples.append(sample)
            else:
                # Stereo
                left = struct.unpack(sample_format, audio_bytes[offset : offset + 2])[0]
                right = struct.unpack(sample_format, audio_bytes[offset + 2 : offset + 4])[0]
                samples.append((left, right))

        # Resample using nearest-neighbor
        ratio = to_sample_rate / from_sample_rate
        new_num_samples = int(num_samples * ratio)

        resampled = []
        for i in range(new_num_samples):
            source_index = int(i / ratio)
            if source_index >= num_samples:
                source_index = num_samples - 1
            resampled.append(samples[source_index])

        # Convert back to bytes
        result = bytearray()
        for sample in resampled:
            if channels == 1:
                result.extend(struct.pack(sample_format, sample))
            else:
                result.extend(struct.pack(sample_format, sample[0]))
                result.extend(struct.pack(sample_format, sample[1]))

        return bytes(result)
