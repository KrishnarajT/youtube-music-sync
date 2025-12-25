import yaml
import os
import sys
from pathlib import Path

class ConfigManager:
    """Handles loading and validating the application configuration."""

    def __init__(self, config_path="config.yml"):
        self.path = config_path
        self.data = self._load()
        self._setup_properties()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: Config file '{self.path}' not found!")
            sys.exit(1)

    def _setup_properties(self):
        self.os_type = self.data.get("os_type", "windows").lower()
        self.input_method = self.data.get("input_method", "channel")
        self.channel_url = self.data.get("channel_url", "")
        self.playlist_urls = self.data.get("playlist_urls", [])
        self.playlist_file = self.data.get("playlist_file", "")

        # Path resolution
        root = self.data.get("root_path", "./downloads")
        if self.os_type == "linux" and root.startswith("~"):
            root = os.path.expanduser(root)
        self.root_path = Path(root)
        self.root_path.mkdir(parents=True, exist_ok=True)

        self.ytdlp_path = self._resolve_exe(self.data.get("ytdlp_path", "yt-dlp"))
        self.ffmpeg_path = self._resolve_exe(self.data.get("ffmpeg_path", ""))

        self.audio_format = str(self.data.get("audio_format", "best")).lower()
        self.audio_quality = str(self.data.get("audio_quality", "0"))
        self.extra_args = self.data.get("extra_args", "")

    def _resolve_exe(self, path):
        if not path:
            return ""
        if "/" not in path and "\\" not in path:
            return path
        if self.os_type == "linux" and path.startswith("~"):
            path = os.path.expanduser(path)
        return path
