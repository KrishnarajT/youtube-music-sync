from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.logging_utils import get_logger
import subprocess
import json
import os
import re
import sys
from tqdm import tqdm

logger = get_logger(__name__)


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
            logger.debug(f"Using cached info for playlist {playlist_id}")
            return cached

        logger.info(f"Fetching playlist info for: {url}")
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
                logger.debug(f"Cached playlist info: {title}")
                return info
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to fetch info for {url}: {e}")
            info = {
                "id": str(playlist_id),
                "title": f"Playlist_{playlist_id}",
                "url": url,
            }
            self.state.cache_info(playlist_id, info)
            return info
        except Exception as e:
            logger.error(f"Error processing playlist info for {url}: {e}")
            info = {
                "id": str(playlist_id),
                "title": f"Playlist_{playlist_id}",
                "url": url,
            }
            self.state.cache_info(playlist_id, info)
            return info

    def from_channel(self):
        """Fetch all playlists from a channel using yt-dlp."""
        logger.info("Fetching playlists from channel...")

        # Try the /playlists URL first
        url = f"{self.config.channel_url}/playlists"
        cmd = [self.config.ytdlp_path, "-J", "--flat-playlist", url]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )

            data = json.loads(result.stdout)

            # Store channel metadata
            channel_info = {
                "channel_id": data.get("channel_id"),
                "channel": data.get("channel"),
                "uploader": data.get("uploader"),
                "uploader_id": data.get("uploader_id"),
                "uploader_url": data.get("uploader_url"),
                "channel_url": data.get("channel_url"),
                "playlist_count": data.get("playlist_count", 0),
            }
            self.state.cache_channel_info(channel_info)
            logger.info(
                f"Found {channel_info['playlist_count']} playlists from channel: {channel_info['channel']}"
            )

            # Extract playlist entries
            playlists = []
            entries = data.get("entries", [])

            for entry in tqdm(entries, desc="Processing playlists", unit="playlist"):
                playlist_id = entry.get("id")
                if not playlist_id:
                    continue

                playlist_info = {
                    "id": str(playlist_id),
                    "title": entry.get("title", f"Playlist_{playlist_id}"),
                    "url": entry.get(
                        "url", f"https://music.youtube.com/playlist?list={playlist_id}"
                    ),
                    "thumbnails": entry.get("thumbnails", []),
                    "ie_key": entry.get("ie_key"),
                }

                # Cache the info
                self.state.cache_info(playlist_id, playlist_info)
                playlists.append(playlist_info)

            logger.info(
                f"Successfully processed {len(playlists)} playlists from channel"
            )
            return playlists

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch playlists from channel: {e}")
            logger.error(f"stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error processing channel: {e}")
            return []

    def from_file(self):
        file_path = self.config.playlist_file
        if not os.path.exists(file_path):
            logger.warning(f"Playlist file not found: {file_path}")
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

        logger.info(f"Processing {len(urls)} playlist URLs from file")
        results = []
        for url in tqdm(urls, desc="Processing file URLs", unit="url"):
            info = self.get_playlist_info(url)
            if info:
                results.append(info)
        logger.info(f"Successfully processed {len(results)} playlists from file")
        return results
