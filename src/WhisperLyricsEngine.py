import subprocess
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel
from utils.vtt_to_lrc import vtt_to_lrc


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
        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type=compute_type,
        )

    def _to_wav(self, audio_path: Path) -> Path:
        """
        Convert audio to mono 16k WAV for Whisper.
        """
        wav_path = audio_path.with_suffix(".wav")

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
            return None

        wav_path = self._to_wav(audio_path)
        vtt_path = audio_path.with_suffix(".vtt")
        lrc_path = audio_path.with_suffix(".lrc")

        try:
            segments, info = self.model.transcribe(
                str(wav_path),
                task="transcribe",
                language=None,  # auto-detect
            )

            # 🔑 Only override Urdu
            if info.language == "ur":
                segments, info = self.model.transcribe(
                    str(wav_path),
                    task="transcribe",
                    language="hi",
                )

            self._write_vtt(segments, vtt_path)
            vtt_to_lrc(vtt_path, lrc_path)

            return lrc_path

        finally:
            if wav_path.exists():
                wav_path.unlink()
