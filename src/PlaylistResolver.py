from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
import subprocess
import json
import os
import re
from tqdm import tqdm


class PlaylistResolver:
    """Resolves playlist IDs and metadata from various input sources."""

    def __init__(self, config: ConfigManager, state: StateManager):
        self.config = config
        self.state = state

    def extract_id(self, url):
        match = re.search(r"list=([^&]+)", url)
        return match.group(1) if match else url.split("/")[-1]

    def get_playlist_info(self, url):
        playlist_id = self.extract_id(url)
        cached = self.state.get_cached_info(playlist_id)
        if cached:
            return cached

        print(f"Fetching info for: {url}")
        cmd = [
            self.config.ytdlp_path,
            "--flat-playlist",
            "--dump-json",
            "--playlist-items",
            "1",
            url,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                data = json.loads(line)
                title = (
                    data.get("playlist_title")
                    or data.get("playlist")
                    or f"Playlist_{playlist_id}"
                )
                info = {"id": str(playlist_id), "title": str(title), "url": url}
                self.state.cache_info(playlist_id, info)
                return info
        except Exception:
            info = {
                "id": str(playlist_id),
                "title": f"Playlist_{playlist_id}",
                "url": url,
            }
            self.state.cache_info(playlist_id, info)
            return info

    def from_channel(self):
        print("Fetching playlists from channel...")
        playlists = []
        urls_to_try = [f"{self.config.channel_url}/playlists", self.config.channel_url]

        for url in urls_to_try:
            cmd = [self.config.ytdlp_path, "--flat-playlist", "--dump-json", url]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", check=True
                )
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("_type") == "playlist":
                        playlists.append(
                            {
                                "id": data["id"],
                                "title": data["title"],
                                "url": data["url"],
                            }
                        )
                if playlists:
                    break
            except subprocess.CalledProcessError:
                continue
        return playlists

    def from_file(self):
        file_path = self.config.playlist_file
        if not os.path.exists(file_path):
            return []

        urls = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "list=" in line:
                    if line.startswith("http"):
                        urls.append(line)
                    else:
                        match = re.search(r"list=([^&\s]+)", line)
                        if match:
                            urls.append(
                                f"https://music.youtube.com/playlist?list={match.group(1)}"
                            )
                elif line.startswith(("PL", "OL")):
                    urls.append(f"https://music.youtube.com/playlist?list={line}")

        results = []
        for url in tqdm(urls, desc="Processing file URLs", unit="url"):
            info = self.get_playlist_info(url)
            if info:
                results.append(info)
        return results
