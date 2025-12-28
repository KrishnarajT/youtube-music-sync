import subprocess
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel
from utils.vtt_to_lrc import vtt_to_lrc
from src.logging_utils import get_logger

logger = get_logger(__name__)


class WhisperLyricsEngine:
    """
    Generates time-synced lyrics using Whisper as a fallback.
    Audio -> WAV -> Whisper -> VTT -> LRC
    """

    def __init__(
        self,
        model_size: str = "small",
        compute_type: str = "int8",
    ):
        logger.info(
            f"Initializing Whisper model: {model_size} (compute_type: {compute_type})"
        )
        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type=compute_type,
        )
        logger.info("Whisper model initialized successfully")

    def _to_wav(self, audio_path: Path) -> Path:
        """
        Convert audio to mono 16k WAV for Whisper.
        """
        wav_path = audio_path.with_suffix(".wav")
        logger.debug(f"Converting {audio_path.name} to WAV format")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(audio_path),
                "-ar",
                "16000",
                "-ac",
                "1",
                str(wav_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

        return wav_path

    def _write_vtt(self, segments, vtt_path: Path):
        """
        Write Whisper segments to a VTT file.
        """

        def fmt(ts: float) -> str:
            h = int(ts // 3600)
            m = int((ts % 3600) // 60)
            s = ts % 60
            return f"{h:02}:{m:02}:{s:06.3f}".replace(".", ",")

        with vtt_path.open("w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for seg in segments:
                f.write(
                    f"{fmt(seg.start)} --> {fmt(seg.end)}\n" f"{seg.text.strip()}\n\n"
                )

    def generate_lrc(self, audio_path: Path) -> Optional[Path]:
        if not audio_path.exists():
            logger.warning(f"Audio file not found: {audio_path}")
            return None

        # Verify file is audio format (mp3 or opus)
        if audio_path.suffix.lower() not in [".mp3", ".opus"]:
            logger.warning(f"Unsupported audio format: {audio_path.suffix}")
            return None

        logger.info(f"Generating LRC lyrics for: {audio_path.name}")
        wav_path = self._to_wav(audio_path)
        vtt_path = audio_path.with_suffix(".vtt")
        lrc_path = audio_path.with_suffix(".lrc")

        try:
            logger.debug(f"Running Whisper transcription on {wav_path.name}")
            segments, info = self.model.transcribe(
                str(wav_path),
                task="transcribe",
                language=None,  # auto-detect
            )

            # 🔑 Only override Urdu
            if info.language == "ur":
                logger.debug("Detected Urdu language, overriding with Hindi")
                segments, info = self.model.transcribe(
                    str(wav_path),
                    task="transcribe",
                    language="hi",
                )

            self._write_vtt(segments, vtt_path)
            vtt_to_lrc(vtt_path, lrc_path)
            logger.info(f"Successfully generated LRC file: {lrc_path.name}")

            return lrc_path

        except Exception as e:
            logger.error(
                f"Failed to generate LRC for {audio_path.name}: {e}", exc_info=True
            )
            return None
        finally:
            if wav_path.exists():
                wav_path.unlink()
                logger.debug(f"Cleaned up temporary WAV file: {wav_path.name}")
