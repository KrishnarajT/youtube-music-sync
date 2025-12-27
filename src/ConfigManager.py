import yaml
import os
import sys
from pathlib import Path
from shutil import which


class ConfigManager:
    """Handles loading and validating the application configuration."""

    def __init__(self, config_path=None):
        # Resolve config path: explicit > env > default
        self.path = config_path or os.getenv("APP_CONFIG_PATH") or "config.yml"
        self.data = self._load()
        self._setup_properties()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: Config file '{self.path}' not found!")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Error: Failed to parse config file: {e}")
            sys.exit(1)

    def _setup_properties(self):
        # Core config
        self.os_type = self.data.get("os_type", "windows").lower()
        self.input_method = self.data.get("input_method", "channel")
        self.channel_url = self.data.get("channel_url", "")

        # Playlist handling
        self.playlist_urls = self.data.get("playlist_urls", [])

        self.playlist_file = self.data.get("playlist_file") or os.getenv(
            "PLAYLISTS_FILE"
        )

        if self.input_method == "playlist_file":
            if not self.playlist_file:
                print(
                    "Error: input_method is 'playlist_file' but no playlist_file was provided"
                )
                sys.exit(1)

            self.playlist_file = str(Path(self.playlist_file).resolve())
            self.playlist_urls = self._load_playlist_file(self.playlist_file)

        # Root path resolution
        root = self.data.get("root_path", "./downloads")
        if self.os_type == "linux" and root.startswith("~"):
            root = os.path.expanduser(root)

        self.root_path = Path(root)
        self.root_path.mkdir(parents=True, exist_ok=True)

        # Executables
        self.ytdlp_path = self._resolve_exe(self.data.get("ytdlp_path", "yt-dlp"))
        self.ffmpeg_path = self._resolve_exe(self.data.get("ffmpeg_path", ""))

        # Audio format normalization
        audio_format_raw = self.data.get("audio_format", "best")
        if audio_format_raw is None or str(audio_format_raw).lower() in ["", "auto"]:
            self.audio_format = "best"
        else:
            self.audio_format = str(audio_format_raw).lower()

        self.audio_quality = str(self.data.get("audio_quality", "0"))
        self.extra_args = self.data.get("extra_args", "")

    def _load_playlist_file(self, path: str) -> list[str]:
        """
        Load playlist URLs from a text file.
        One URL per line. Empty lines and comments (#) are ignored.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]

            if not lines:
                raise ValueError("Playlist file is empty")

            return lines

        except FileNotFoundError:
            print(f"Error: Playlist file '{path}' not found!")
            sys.exit(1)
        except Exception as e:
            print(f"Error: Failed to load playlist file '{path}': {e}")
            sys.exit(1)

    def _resolve_exe(self, path):
        """Resolve executable path, finding it in PATH if needed"""
        if not path:
            return ""

        # Bare command name → search PATH
        if "/" not in path and "\\" not in path:
            found = which(path)
            return found if found else path

        # Expand home directory if needed
        if self.os_type == "linux" and path.startswith("~"):
            path = os.path.expanduser(path)

        return str(Path(path).resolve())
