from src.ConfigManager import ConfigManager
import subprocess
import re


class DownloadEngine:
    """Wraps the yt-dlp execution and manages the download process."""

    def __init__(self, config: ConfigManager):
        self.config = config

    def clean_filename(self, name):
        regex = r'[<>:"/\\|?*]' if self.config.os_type == "windows" else r"[/\0]"
        cleaned = re.sub(regex, "", name).strip(". ")
        return cleaned[:200]

    def download(self, playlist_info):
        clean_title = self.clean_filename(playlist_info["title"])
        dest_dir = self.config.root_path / clean_title
        dest_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.config.ytdlp_path,
            "--extract-audio",
            "--audio-format",
            "best",
            "--audio-quality",
            self.config.audio_quality,
            "--embed-thumbnail",
            "--embed-metadata",
            "--add-metadata",
            "--no-overwrites",
            "--ignore-errors",
            "--output",
            str(dest_dir / "%(title)s.%(ext)s"),
            playlist_info["url"],
        ]

        if self.config.extra_args:
            cmd.extend(self.config.extra_args.split())

        download_started = False
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        )

        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                if "[download]" in line and "%" in line:
                    download_started = True
                    print(f"\r{line}", end="", flush=True)
                elif any(
                    x in line
                    for x in [
                        "[download] Destination:",
                        "ERROR",
                        "WARNING",
                        "[ExtractAudio]",
                    ]
                ):
                    if "SABR streaming" not in line:  # Filtering noise
                        print(f"\n{line}")
        except UnicodeDecodeError:
            pass

        process.wait()
        return process.returncode == 0 or download_started
