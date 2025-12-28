import json
from pathlib import Path
from src.logging_utils import get_logger

logger = get_logger(__name__)


class StateManager:
    """Manages the persistence of download progress and metadata caching."""

    def __init__(self, file_path="download_state.json"):
        self.file_path = Path(file_path)
        self.state = self._load()

    def _load(self):
        default_state = {
            "completed_playlists": [],
            "partially_downloaded": {},
            "playlist_info": {},
            "channel_info": {},
        }
        if not self.file_path.exists():
            logger.info(f"State file {self.file_path} not found, using default state")
            return default_state
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                logger.info(f"Loaded state from {self.file_path}")
                loaded_state = json.loads(content) if content else default_state
                # Ensure channel_info exists in loaded state
                if "channel_info" not in loaded_state:
                    loaded_state["channel_info"] = {}
                return loaded_state
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                f"State file {self.file_path} is corrupted, using default state"
            )
            return default_state

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            logger.debug(f"State saved to {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def is_completed(self, playlist_id):
        return str(playlist_id) in self.state["completed_playlists"]

    def mark_completed(self, playlist_id):
        pid = str(playlist_id)
        if pid not in self.state["completed_playlists"]:
            self.state["completed_playlists"].append(pid)
            self.save()

    def get_cached_info(self, playlist_id):
        return self.state.get("playlist_info", {}).get(str(playlist_id))

    def cache_info(self, playlist_id, info):
        if "playlist_info" not in self.state:
            self.state["playlist_info"] = {}
        self.state["playlist_info"][str(playlist_id)] = info
        self.save()

    def cache_channel_info(self, channel_info):
        """Cache channel metadata."""
        self.state["channel_info"] = channel_info
        self.save()
        logger.info(
            f"Cached channel info for: {channel_info.get('channel', 'Unknown')}"
        )

    def get_channel_info(self):
        """Get cached channel information."""
        return self.state.get("channel_info", {})

    def get_all_playlists(self):
        """Get all cached playlist information."""
        return self.state.get("playlist_info", {})

    def get_stats(self):
        """Get statistics about cached data."""
        return {
            "total_playlists": len(self.state.get("playlist_info", {})),
            "completed_playlists": len(self.state.get("completed_playlists", [])),
            "partial_downloads": len(self.state.get("partially_downloaded", {})),
            "channel_cached": bool(self.state.get("channel_info", {})),
        }
