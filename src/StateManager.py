import json
from pathlib import Path


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
        }
        if not self.file_path.exists():
            return default_state
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else default_state
        except (json.JSONDecodeError, ValueError):
            return default_state

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[STATE ERROR] Failed to save state: {e}")

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
