import sys
import time
from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine


class YouTubeApp:
    """
    Orchestrates the components to run the application via Command Line.
    This uses the same logic as dashboard.py but formatted for terminal output.
    """

    def __init__(self):
        try:
            self.config = ConfigManager()
            self.state = StateManager()
            self.resolver = PlaylistResolver(self.config, self.state)
            self.engine = DownloadEngine(self.config)
        except Exception as e:
            print(f"Failed to initialize components: {e}")
            sys.exit(1)

    def run(self):
        print("\n" + "=" * 60)
        print("🎵 YouTube Music Sync (CLI Mode)")
        print("=" * 60 + "\n")

        # 1. Resolve Target Playlists based on Config Method
        print(f"Method: {self.config.input_method}")
        with getattr(
            self, "_loading_spinner", lambda: None
        )():  # Placeholder for context
            if self.config.input_method == "channel":
                playlists = self.resolver.from_channel()
            elif self.config.input_method == "playlist_file":
                playlists = self.resolver.from_file()
            else:
                playlists = [
                    self.resolver.get_playlist_info(url)
                    for url in self.config.playlist_urls
                ]

        # Filter out failed metadata fetches
        playlists = [p for p in playlists if p]
        if not playlists:
            print("❌ No playlists found! Check your config or internet connection.")
            return

        # 2. Filtering and Reporting
        remaining = [p for p in playlists if not self.state.is_completed(p["id"])]

        print(f"📊 Summary:")
        print(f"   Total Playlists: {len(playlists)}")
        print(f"   Already Synced:  {len(playlists) - len(remaining)}")
        print(f"   Pending Sync:    {len(remaining)}")

        if not remaining:
            print("\n✅ All playlists are up to date!")
            return

        # 3. Processing Loop
        print("\n🚀 Starting Sync...")
        for i, p in enumerate(remaining, 1):
            print(f"\n[{i}/{len(remaining)}] Processing: {p['title']}")
            print(f"ID: {p['id']}")

            success = self.engine.download(p)

            if success:
                self.state.mark_completed(p["id"])
                print(f"✓ State saved for: {p['title']}")
                # Brief pause to be polite to the API
                time.sleep(1)
            else:
                print(f"⚠️ Failed to complete sync for: {p['title']}")

        print("\n" + "=" * 60)
        print("✨ All tasks finished!")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        app = YouTubeApp()
        app.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user. Progress up to this point has been saved.")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 A fatal error occurred: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
