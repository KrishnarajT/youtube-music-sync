from src.ConfigManager import ConfigManager
from src.logging_utils import get_logger
import subprocess
import re
import os
import requests
from pathlib import Path
from utils.vtt_to_lrc import vtt_to_lrc

logger = get_logger(__name__)


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

    def download_cover_image(self, playlist_info: dict, dest_dir: Path) -> bool:
        """
        Download the playlist cover image from thumbnails and save it as 'cover.jpg' or 'cover.png'.
        Returns True if successful, False otherwise.
        """
        thumbnails = playlist_info.get("thumbnails", [])

        if not thumbnails:
            logger.warning(
                f"No thumbnails found for playlist: {playlist_info.get('title', 'Unknown')}"
            )
            return False

        # Sort thumbnails by resolution (highest first) and get the best quality
        sorted_thumbnails = sorted(
            thumbnails,
            key=lambda t: (t.get("height", 0) * t.get("width", 0)),
            reverse=True,
        )

        for thumbnail in sorted_thumbnails:
            url = thumbnail.get("url")
            if not url:
                continue

            try:
                logger.info(f"Downloading cover image from: {url}")
                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()

                # Determine file extension from content-type or URL
                content_type = response.headers.get("content-type", "")
                if (
                    "jpeg" in content_type
                    or "jpg" in content_type
                    or url.endswith((".jpg", ".jpeg"))
                ):
                    ext = "jpg"
                elif "png" in content_type or url.endswith(".png"):
                    ext = "png"
                elif "webp" in content_type or url.endswith(".webp"):
                    ext = "webp"
                else:
                    ext = "jpg"  # Default to jpg

                cover_path = dest_dir / f"cover.{ext}"

                # Download and save the image
                with open(cover_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                logger.info(f"Successfully saved cover image: {cover_path.name}")
                return True

            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to download thumbnail from {url}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error saving cover image: {e}")
                continue

        logger.warning("Failed to download any cover image")
        return False

    def convert_opus_to_mp3(self, dest_dir: Path) -> None:
        """
        Convert all .opus files to .mp3 using ffmpeg and delete the original opus files.
        """
        opus_files = list(dest_dir.glob("*.opus"))
        if not opus_files:
            logger.debug("No opus files found to convert")
            return

        logger.info(f"Converting {len(opus_files)} opus file(s) to mp3...")

        for opus_file in opus_files:
            mp3_file = opus_file.with_suffix(".mp3")

            try:
                logger.debug(f"Converting: {opus_file.name} → {mp3_file.name}")

                subprocess.run(
                    [
                        "ffmpeg",
                        "-i",
                        str(opus_file),
                        "-codec:a",
                        "libmp3lame",
                        "-q:a",
                        "2",  # Quality: 2 is high quality (~192kbps)
                        str(mp3_file),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )

                # Delete the original opus file
                opus_file.unlink()
                logger.info(f"Converted and deleted: {opus_file.name}")

            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to convert {opus_file.name} to mp3: {e}")
            except Exception as e:
                logger.error(f"Error during conversion of {opus_file.name}: {e}")

    def download(self, playlist_info: dict) -> bool:
        """
        Executes the yt-dlp download process for a given playlist.
        Returns True if the sync is considered successful (even if some videos are missing).
        """
        clean_title = self.clean_filename(playlist_info["title"])
        dest_dir = self.config.root_path / clean_title
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Download cover image first
        logger.info(f"Downloading cover image for playlist: {clean_title}")
        self.download_cover_image(playlist_info, dest_dir)

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

        logger.info(f"Target Directory: {dest_dir}")
        logger.debug(f"Executing yt-dlp command for playlist: {clean_title}")

        download_started = False
        error_occurred = False
        error_logs = []

        try:
            # Pre-flight check: Ensure yt-dlp executable exists if a full path was provided
            if "\\" in self.config.ytdlp_path or "/" in self.config.ytdlp_path:
                if not Path(self.config.ytdlp_path).exists():
                    logger.error(
                        f"yt-dlp executable not found at: {self.config.ytdlp_path}"
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
                    logger.info(f"   {line}")
                    download_started = True

                # Check for errors
                if "error:" in line.lower() and "ignore" not in line.lower():
                    # Handle common non-fatal YouTube errors (unavailable/private videos)
                    if (
                        "video unavailable" in line.lower()
                        or "private video" in line.lower()
                    ):
                        logger.warning(f"Skipping unavailable video: {line}")
                        continue

                    error_occurred = True
                    error_logs.append(line)
                    logger.error(f"{line}")

                # Print other relevant warnings or status messages
                elif any(
                    x in line.lower() for x in ["warning", "postprocess", "ffmpeg"]
                ):
                    logger.info(f"   {line}")

            process.wait()

            # Logic: Success if return code is 0 OR if we managed to process/skip videos despite minor errors
            success = process.returncode == 0 or (
                download_started and not error_occurred
            )

            if not success:
                logger.error(f"Download failed for: {playlist_info['title']}")
                logger.error(f"Exit Code: {process.returncode}")
                if error_logs:
                    logger.error("Captured Error Messages:")
                    for err in error_logs[-5:]:
                        logger.error(f"  {err}")
                    logger.error("Check the URL or your network connection.")
                    return False

            # ---- Post-process: Convert OPUS to MP3 ----
            self.convert_opus_to_mp3(dest_dir)

            # ---- Post-process: VTT → LRC ----
            if getattr(self.config, "download_lyrics", False):
                for vtt_file in dest_dir.glob("*.vtt"):
                    lrc_file = vtt_file.with_suffix(".lrc")
                    try:
                        vtt_to_lrc(vtt_file, lrc_file)
                        logger.info(
                            f"Converted VTT to LRC: {vtt_file.name} → {lrc_file.name}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to convert {vtt_file.name}: {e}")

            logger.info(
                f"Successfully completed download for: {playlist_info['title']}"
            )
            return True

        except Exception as e:
            logger.error(f"Download Engine exception: {e}", exc_info=True)
            return False
