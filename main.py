import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine
from src.WhisperLyricsEngine import WhisperLyricsEngine
from src.logging_utils import get_logger

logger = get_logger(__name__)


class YouTubeApp:
    """
    Orchestrates the components to run the application automatically
    on a 12-hour schedule.
    """

    def __init__(self):
        try:
            logger.info("Initializing components...")
            self.config = ConfigManager()
            logger.info(f"Config loaded (Method: {self.config.input_method})")
            logger.info(f"yt-dlp path: {self.config.ytdlp_path}")
            logger.info(f"Root path: {self.config.root_path}")

            self.state = StateManager()
            self.lyrics_engine = WhisperLyricsEngine()
            self.resolver = PlaylistResolver(self.config, self.state)
            self.engine = DownloadEngine(self.config)
            logger.info("All components initialized")
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}", exc_info=True)
            sys.exit(1)

    def run_album_naming(self) -> None:
        """
        Executes name_album_from_folders.py on the root download directory.
        This automatically tags all MP3 files with proper album/artist metadata.
        """
        try:
            from name_album_from_folders import NameAlbumFromFolders

            logger.info(f"Running album naming on: {self.config.root_path}")
            namer = NameAlbumFromFolders(self.config.root_path)
            namer.run()
            logger.info("Album naming completed")
        except ImportError:
            logger.warning(
                "name_album_from_folders module not found; skipping album naming"
            )
        except Exception as e:
            logger.error(f"Album naming failed: {e}", exc_info=True)

    def perform_sync(self):
        """Single sync pass logic."""
        logger.info(f"Sync started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 1. Resolve Target Playlists (Fetches latest songs from URLs/Channels)
        logger.info(f"Input Method: {self.config.input_method}")
        if self.config.input_method == "channel":
            playlists = self.resolver.from_channel()
        elif self.config.input_method == "playlist_file":
            playlists = self.resolver.from_file()
        else:
            playlists = [
                self.resolver.get_playlist_info(url)
                for url in self.config.playlist_urls
            ]

        playlists = [p for p in playlists if p]
        if not playlists:
            logger.warning(
                "No playlists found! Check your config or internet connection."
            )
            return

        logger.info(f"Found {len(playlists)} playlists to check.")

        # 2. Processing Loop
        # Note: We no longer filter by 'self.state.is_completed' here.
        # This allows yt-dlp to check the playlist for new songs every 12 hours.
        success_count = 0
        fail_count = 0

        for i, p in enumerate(playlists, 1):
            logger.info(f"[{i}/{len(playlists)}] Checking for updates: {p['title']}")

            try:
                # DownloadEngine handles skipping existing files via download_archive.txt
                success = self.engine.download(p)

                if success:
                    # Whisper lyrics fallback for any new songs
                    playlist_dir = self.config.root_path / self.engine.clean_filename(
                        p["title"]
                    )
                    for audio_file in playlist_dir.glob("*.mp3"):
                        lrc_file = audio_file.with_suffix(".lrc")
                        if not lrc_file.exists():
                            try:
                                self.lyrics_engine.generate_lrc(audio_file)
                                logger.info(f"Lyrics generated for {audio_file.name}")
                            except Exception as e:
                                logger.warning(
                                    f"Failed lyrics for {audio_file.name}: {e}"
                                )

                    success_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                logger.error(
                    f"Exception during sync of {p['title']}: {e}", exc_info=True
                )
                fail_count += 1

        logger.info(
            f"Sync Cycle Finished! Successful/Up-to-date: {success_count}, Failed: {fail_count}"
        )

        # Run album naming script on all downloaded files
        logger.info("Starting album naming process...")
        self.run_album_naming()
        logger.info("Album naming process completed")

    def run_forever(self):
        """Runs the sync every 12 hours."""
        INTERVAL = 12 * 60 * 60  # 12 Hours in seconds

        logger.info("YouTube Music Sync (Automated Mode) started")
        logger.info(f"Cycle Interval: 12 Hours")

        while True:
            try:
                self.perform_sync()
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)

            next_run = datetime.now() + timedelta(seconds=INTERVAL)
            logger.info(
                f"Sleeping. Next sync scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        app = YouTubeApp()
        app.run_forever()
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"A fatal error occurred: {e}", exc_info=True)
        sys.exit(1)
