from src.ConfigManager import ConfigManager
import subprocess
import re
import os
from pathlib import Path
from utils.vtt_to_lrc import vtt_to_lrc


class DownloadEngine:
    """
    Wraps yt-dlp execution and manages audio + optional lyric downloads.
    """

    def __init__(self, config: ConfigManager):
        self.config = config

    def clean_filename(self, name: str) -> str:
        """Cleans a string to be a safe filename based on OS type."""
        regex = r'[<>:"/\\|?*]' if self.config.os_type == "windows" else r"[/\0]"
        cleaned = re.sub(regex, "", name).strip(". ")
        return cleaned[:200]

    def download(self, playlist_info: dict) -> bool:
        """
        Executes the yt-dlp download process for a given playlist.
        Returns True if the sync is considered successful (even if some videos are missing).
        """
        clean_title = self.clean_filename(playlist_info["title"])
        dest_dir = self.config.root_path / clean_title
        dest_dir.mkdir(parents=True, exist_ok=True)

        archive_file = "download_archive.txt"

        # Build the command
        cmd = [
            self.config.ytdlp_path,
            "--extract-audio",
            "--audio-format",
            self.config.audio_format,
            "--audio-quality",
            self.config.audio_quality,
            "--embed-thumbnail",
            "--embed-metadata",
            "--add-metadata",
            "--download-archive",
            str(archive_file),
            "--no-overwrites",
            "--ignore-errors",
        ]

        # Add ffmpeg path if specified in config
        if getattr(self.config, "ffmpeg_path", None):
            cmd.extend(["--ffmpeg-location", self.config.ffmpeg_path])

        # ---- Lyrics / captions support ----
        if getattr(self.config, "download_lyrics", False):
            cmd.extend(
                [
                    "--write-subs",
                    "--write-auto-subs",
                    "--sub-langs",
                    "en",
                    "--sub-format",
                    "vtt",
                ]
            )

        if getattr(self.config, "lyrics_only", False):
            cmd.append("--skip-download")

        # ---- Output & URL ----
        cmd.extend(
            [
                "--output",
                str(dest_dir / "%(title)s.%(ext)s"),
                playlist_info["url"],
            ]
        )

        if self.config.extra_args:
            cmd.extend(self.config.extra_args.split())

        print(f"\n[DEBUG] Target Directory: {dest_dir}")
        print(f"[DEBUG] Executing Command:\n{' '.join(cmd)}\n")

        download_started = False
        error_occurred = False
        error_logs = []

        try:
            # Pre-flight check: Ensure yt-dlp executable exists if a full path was provided
            if "\\" in self.config.ytdlp_path or "/" in self.config.ytdlp_path:
                if not Path(self.config.ytdlp_path).exists():
                    print(
                        f"❌ [ERROR] yt-dlp executable not found at: {self.config.ytdlp_path}"
                    )
                    return False

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                shell=self.config.os_type == "windows",
                encoding="utf-8",
                errors="replace",
            )

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                # Detect if activity happened (new download, extraction, or skipping archived items)
                if any(
                    x in line.lower()
                    for x in [
                        "[download]",
                        "[extractaudio]",
                        "already been recorded in the archive",
                    ]
                ):
                    print(f"   {line}")
                    download_started = True

                # Check for errors
                if "error:" in line.lower() and "ignore" not in line.lower():
                    # Handle common non-fatal YouTube errors (unavailable/private videos)
                    if (
                        "video unavailable" in line.lower()
                        or "private video" in line.lower()
                    ):
                        print(f"   ⚠️ Skipping: {line}")
                        continue

                    error_occurred = True
                    error_logs.append(line)
                    print(f"   ❌ {line}")

                # Print other relevant warnings or status messages
                elif any(
                    x in line.lower() for x in ["warning", "postprocess", "ffmpeg"]
                ):
                    print(f"   {line}")

            process.wait()

            # Logic: Success if return code is 0 OR if we managed to process/skip videos despite minor errors
            success = process.returncode == 0 or (
                download_started and not error_occurred
            )

            if not success:
                print("\n" + "!" * 60)
                print(f"FAILED: {playlist_info['title']}")
                print(f"Exit Code: {process.returncode}")
                if error_logs:
                    print("Captured Error Messages:")
                    for err in error_logs[-5:]:
                        print(f"  - {err}")
                print("Check the URL or your network connection.")
                print("!" * 60 + "\n")
                return False

            # ---- Post-process: VTT → LRC ----
            if getattr(self.config, "download_lyrics", False):
                for vtt_file in dest_dir.glob("*.vtt"):
                    lrc_file = vtt_file.with_suffix(".lrc")
                    try:
                        vtt_to_lrc(vtt_file, lrc_file)
                        print(f"[LYRICS] Converted {vtt_file.name} → {lrc_file.name}")
                    except Exception as e:
                        print(f"[LYRICS] Failed to convert {vtt_file.name}: {e}")

            return True

        except Exception as e:
            print(f"\n💥 [CRITICAL EXCEPTION] Download Engine failed: {e}")
            import traceback

            traceback.print_exc()
            return False
