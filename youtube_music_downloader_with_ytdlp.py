import yaml
import subprocess
import json
import os
import re
import sys
from pathlib import Path
from tqdm import tqdm
import time


class YouTubePlaylistDownloader:
    def __init__(self, config_path="config.yml"):
        self.config_path = config_path
        self.load_config()
        self.state_file = Path("download_state.json")
        self.load_state()

    def load_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self.os_type = config.get("os_type", "windows").lower()
            self.input_method = config.get("input_method", "channel")
            self.channel_url = config.get("channel_url", "")
            self.playlist_urls = config.get("playlist_urls", [])
            self.playlist_file = config.get("playlist_file", "")

            # Handle path expansion for Linux home directory
            root_path = config["root_path"]
            if self.os_type == "linux" and root_path.startswith("~"):
                root_path = os.path.expanduser(root_path)
            self.root_path = Path(root_path)

            # Handle executable paths
            self.ytdlp_path = self._resolve_executable_path(config["ytdlp_path"])
            self.ffmpeg_path = self._resolve_executable_path(
                config.get("ffmpeg_path", "")
            )

            # Handle audio format with safe defaults
            audio_format_raw = config.get("audio_format")
            if audio_format_raw is None or audio_format_raw == "":
                self.audio_format = "auto"
            else:
                self.audio_format = str(audio_format_raw).lower()

            audio_quality_raw = config.get("audio_quality")
            if audio_quality_raw is None or audio_quality_raw == "":
                self.audio_quality = "0"
            else:
                self.audio_quality = str(audio_quality_raw)

            self.extra_args = config.get("extra_args", "")

            # Create root directory if it doesn't exist
            self.root_path.mkdir(parents=True, exist_ok=True)

            print(f"✓ Configuration loaded successfully")
            print(f"  OS Type: {self.os_type}")
            print(f"  Input Method: {self.input_method}")
            if self.input_method == "channel":
                print(f"  Channel: {self.channel_url}")
            elif self.input_method == "playlist_file":
                print(f"  Playlist File: {self.playlist_file}")
            else:
                print(f"  Playlist URLs: {len(self.playlist_urls)} playlists")
            print(f"  Root Path: {self.root_path}")
            print(f"  yt-dlp: {self.ytdlp_path}")
            if self.ffmpeg_path:
                print(f"  ffmpeg: {self.ffmpeg_path}")
            print(f"  Audio Format: {self.audio_format}")
            if self.audio_format != "auto":
                print(f"  Audio Quality: {self.audio_quality}")
            print()

        except FileNotFoundError:
            print(f"Error: Config file '{self.config_path}' not found!")
            sys.exit(1)
        except KeyError as e:
            print(f"Error: Missing required config key: {e}")
            sys.exit(1)

    def _resolve_executable_path(self, path):
        """Resolve executable path, handling PATH lookup if just a command name"""
        if not path:
            return ""

        # If it's just a command name (no path separators), return as-is to use PATH
        if "/" not in path and "\\" not in path:
            return path

        # Otherwise, expand home directory if needed and return full path
        if self.os_type == "linux" and path.startswith("~"):
            path = os.path.expanduser(path)

        return path

    def load_state(self):
        """Load download state for continuity support"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        self.state = json.loads(content)
                    else:
                        # File exists but is empty
                        print(
                            "Note: State file exists but is empty, creating new state"
                        )
                        self.state = {
                            "completed_playlists": [],
                            "partially_downloaded": {},
                            "playlist_info": {},
                        }
                        self.save_state()
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Warning: Could not parse state file ({e}), creating new state")
                self.state = {
                    "completed_playlists": [],
                    "partially_downloaded": {},
                    "playlist_info": {},
                }
                self.save_state()
        else:
            self.state = {
                "completed_playlists": [],
                "partially_downloaded": {},
                "playlist_info": {},
            }
            # Create the file immediately
            self.save_state()
            print(f"Created new state file: {self.state_file.absolute()}")

    def save_state(self):
        """Save download state"""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            print(f"[STATE SAVED] File written to: {self.state_file.absolute()}")
        except Exception as e:
            print(f"[STATE ERROR] Failed to save state: {e}")
            import traceback

            traceback.print_exc()

    def clean_filename(self, name):
        """Clean playlist name for use as directory name"""
        if self.os_type == "windows":
            # Remove invalid characters for Windows
            cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
        else:
            # Remove invalid characters for Linux (less restrictive)
            cleaned = re.sub(r"[/\0]", "", name)

        # Remove leading/trailing spaces and dots
        cleaned = cleaned.strip(". ")
        # Limit length
        cleaned = cleaned[:200]
        return cleaned

    def extract_playlist_urls_from_file(self, file_path):
        """Extract playlist URLs from a text file"""
        print(f"Reading playlist URLs from: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"Error: File '{file_path}' not found!")
            return []

        playlist_urls = []

        for line in lines:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Extract playlist URL if it contains 'list='
            if "list=" in line:
                # Extract the full URL or just the list parameter
                if line.startswith("http"):
                    playlist_urls.append(line)
                else:
                    # If it's just a playlist ID, construct the URL
                    match = re.search(r"list=([^&\s]+)", line)
                    if match:
                        playlist_id = match.group(1)
                        # Default to YouTube Music format
                        playlist_urls.append(
                            f"https://music.youtube.com/playlist?list={playlist_id}"
                        )
            elif line.startswith("PL") or line.startswith("OL"):
                # If it's just a playlist ID without 'list='
                playlist_urls.append(f"https://music.youtube.com/playlist?list={line}")

        print(f"✓ Found {len(playlist_urls)} playlist URLs in file\n")
        return playlist_urls

    def get_playlist_info(self, playlist_url):
        """Get playlist title and ID from URL, with caching"""
        playlist_id = self.extract_playlist_id(playlist_url)

        # Check cache first
        if playlist_id in self.state.get("playlist_info", {}):
            cached = self.state["playlist_info"][playlist_id]
            print(f"Using cached info for: {cached['title']}")
            return cached

        print(f"Fetching info for: {playlist_url}")

        cmd = [
            self.ytdlp_path,
            "--flat-playlist",
            "--dump-json",
            "--playlist-items",
            "1",
            playlist_url,
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
                if line:
                    try:
                        data = json.loads(line)
                        # Get playlist info from the entry
                        playlist_title = (
                            data.get("playlist_title")
                            or data.get("playlist")
                            or f"Playlist_{playlist_id}"
                        )

                        # Ensure we have valid strings
                        if not playlist_title or playlist_title == "None":
                            playlist_title = f"Playlist_{playlist_id}"

                        playlist_info = {
                            "id": str(playlist_id),
                            "title": str(playlist_title),
                            "url": playlist_url,
                        }

                        # Cache the info
                        if "playlist_info" not in self.state:
                            self.state["playlist_info"] = {}
                        self.state["playlist_info"][playlist_id] = playlist_info
                        self.save_state()

                        return playlist_info
                    except (json.JSONDecodeError, AttributeError, TypeError) as e:
                        print(f"Warning: Could not parse JSON: {e}")
                        continue

            # Fallback if JSON parsing fails
            playlist_info = {
                "id": str(playlist_id),
                "title": f"Playlist_{playlist_id}",
                "url": playlist_url,
            }

            # Cache even the fallback
            if "playlist_info" not in self.state:
                self.state["playlist_info"] = {}
            self.state["playlist_info"][playlist_id] = playlist_info
            self.save_state()

            return playlist_info

        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not fetch info for playlist: {e.stderr}")
            playlist_info = {
                "id": str(playlist_id),
                "title": f"Playlist_{playlist_id}",
                "url": playlist_url,
            }

            # Cache even errors
            if "playlist_info" not in self.state:
                self.state["playlist_info"] = {}
            self.state["playlist_info"][playlist_id] = playlist_info
            self.save_state()

            return playlist_info

    def extract_playlist_id(self, url):
        """Extract playlist ID from URL"""
        match = re.search(r"list=([^&]+)", url)
        if match:
            return match.group(1)
        return url.split("/")[-1]

    def get_playlists_from_channel(self):
        """Fetch all public playlists from the channel"""
        print("Fetching playlists from channel...")
        print(
            "Note: This only works for regular YouTube channels, not YouTube Music channels\n"
        )

        # Try different channel URL formats
        channel_urls_to_try = [
            f"{self.channel_url}/playlists",
            f"{self.channel_url}/playlists?view=1",
            self.channel_url,
        ]

        playlists = []

        for channel_url in channel_urls_to_try:
            cmd = [self.ytdlp_path, "--flat-playlist", "--dump-json", channel_url]

            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", check=True
                )

                for line in result.stdout.strip().split("\n"):
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get("_type") == "playlist":
                                playlists.append(
                                    {
                                        "id": data["id"],
                                        "title": data["title"],
                                        "url": data["url"],
                                    }
                                )
                        except json.JSONDecodeError:
                            continue

                if playlists:
                    print(f"✓ Found {len(playlists)} playlists\n")
                    return playlists

            except subprocess.CalledProcessError as e:
                continue

        print("⚠ No playlists found via channel URL")
        print(
            "Tip: For YouTube Music, use 'playlist_urls' or 'playlist_file' method instead\n"
        )
        return []

    def get_playlists_from_urls(self):
        """Get playlist info from direct URLs"""
        print("Processing playlist URLs...")
        playlists = []

        with tqdm(
            total=len(self.playlist_urls),
            desc="Fetching playlist info",
            unit="playlist",
        ) as pbar:
            for url in self.playlist_urls:
                playlist = self.get_playlist_info(url)
                if playlist:
                    playlists.append(playlist)
                pbar.update(1)

        print(f"\n✓ Processed {len(playlists)} playlists\n")
        return playlists

    def get_playlists_from_file(self):
        """Get playlist info from URLs in a file"""
        urls = self.extract_playlist_urls_from_file(self.playlist_file)

        if not urls:
            return []

        print("Processing playlist URLs from file...")
        playlists = []

        with tqdm(
            total=len(urls), desc="Fetching playlist info", unit="playlist"
        ) as pbar:
            for url in urls:
                playlist = self.get_playlist_info(url)
                if playlist:
                    playlists.append(playlist)
                pbar.update(1)

        print(f"\n✓ Processed {len(playlists)} playlists\n")
        return playlists

    def download_playlist(self, playlist):
        """Download a single playlist with progress tracking"""
        playlist_id = str(playlist["id"])
        playlist_title = str(playlist["title"])

        # Check if already completed
        if playlist_id in self.state["completed_playlists"]:
            print(f"⊙ Skipping '{playlist_title}' (already completed)")
            return True

        print(f"\n[STATE CHECK] Playlist ID: {playlist_id}")
        print(f"[STATE CHECK] Completed playlists: {self.state['completed_playlists']}")
        print(f"[STATE CHECK] State file location: {self.state_file.absolute()}")

        # Create playlist directory
        clean_title = self.clean_filename(playlist_title)
        playlist_dir = self.root_path / clean_title
        playlist_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"Downloading: {playlist_title}")
        print(f"Destination: {playlist_dir}")
        print(f"{'='*60}\n")

        # Build yt-dlp command - simple audio download with metadata
        cmd = [
            self.ytdlp_path,
            "--extract-audio",
            "--audio-format",
            "best",
            "--audio-quality",
            "0",
            "--embed-thumbnail",
            "--embed-metadata",
            "--add-metadata",
            "--output",
            str(playlist_dir / "%(title)s.%(ext)s"),
            "--no-overwrites",
            "--ignore-errors",
            playlist["url"],
        ]

        # Add extra args if specified
        if self.extra_args:
            cmd.extend(self.extra_args.split())

        try:
            # Run subprocess with simpler output handling (like the original)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
            )

            download_started = False

            # Track progress
            try:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        # Show download progress
                        if "[download]" in line and "%" in line:
                            download_started = True
                            print(f"\r{line}", end="", flush=True)
                        elif "[download] Destination:" in line:
                            download_started = True
                            print(f"\n{line}")
                        elif "ERROR" in line:
                            print(f"\n{line}")
                        elif "WARNING" in line:
                            # Don't print every warning to reduce noise
                            if (
                                "JavaScript runtime" not in line
                                and "SABR streaming" not in line
                            ):
                                print(f"\n{line}")
                        elif (
                            "[ExtractAudio]" in line
                            or "[EmbedThumbnail]" in line
                            or "[Metadata]" in line
                        ):
                            print(f"\n{line}")
                        elif "[download] Downloading" in line:
                            print(f"\n{line}")
            except UnicodeDecodeError:
                # If we hit encoding issues, just let the process finish
                pass

            process.wait()

            # Consider it successful if downloads started and process completed
            if process.returncode == 0 or (
                download_started and process.returncode == 1
            ):
                print(f"\n✓ Completed: {playlist_title}")
                print(f"[STATE] Adding playlist ID to completed: {playlist_id}")
                self.state["completed_playlists"].append(playlist_id)
                self.save_state()
                print(
                    f"[STATE] State saved. Total completed: {len(self.state['completed_playlists'])}\n"
                )
                return True
            else:
                print(f"\n⚠ Completed with errors: {playlist_title}")
                # Still mark as complete if some downloads happened
                if download_started:
                    print(
                        f"[STATE] Adding playlist ID to completed (with errors): {playlist_id}"
                    )
                    self.state["completed_playlists"].append(playlist_id)
                    self.save_state()
                    print(
                        f"[STATE] State saved. Total completed: {len(self.state['completed_playlists'])}\n"
                    )
                return False

        except Exception as e:
            print(f"\n✗ Error downloading playlist: {e}")
            import traceback

            traceback.print_exc()
            print()
            return False

    def run(self):
        """Main execution function"""
        print("\n" + "=" * 60)
        print("YouTube Playlist Downloader")
        print("=" * 60 + "\n")

        print(f"[STATE] State file location: {self.state_file.absolute()}")
        print(f"[STATE] State file exists: {self.state_file.exists()}")
        print(
            f"[STATE] Current completed playlists: {self.state['completed_playlists']}\n"
        )

        # Get playlists based on input method
        if self.input_method == "channel":
            playlists = self.get_playlists_from_channel()
        elif self.input_method == "playlist_file":
            playlists = self.get_playlists_from_file()
        else:
            playlists = self.get_playlists_from_urls()

        if not playlists:
            print("No playlists to download!")
            return

        print(f"\n[STATE] Checking which playlists are already completed...")
        for p in playlists:
            status = (
                "✓ COMPLETED"
                if str(p["id"]) in self.state["completed_playlists"]
                else "○ PENDING"
            )
            print(f"  {status} - {p['title']} (ID: {p['id']})")
        print()

        # Filter out already completed playlists for progress display
        remaining = [
            p
            for p in playlists
            if str(p["id"]) not in self.state["completed_playlists"]
        ]
        completed_count = len(playlists) - len(remaining)

        print(f"Progress: {completed_count}/{len(playlists)} playlists completed")
        print(f"Remaining: {len(remaining)} playlists\n")

        if not remaining:
            print("All playlists already downloaded!")
            return

        # Download each playlist with progress bar
        with tqdm(
            total=len(remaining), desc="Overall Progress", unit="playlist"
        ) as pbar:
            for playlist in remaining:
                success = self.download_playlist(playlist)
                pbar.update(1)

                # Small delay between playlists
                if success:
                    time.sleep(1)

        print("\n" + "=" * 60)
        print("Download Complete!")
        print("=" * 60)
        print(f"Total playlists: {len(playlists)}")
        print(f"Downloaded: {len(self.state['completed_playlists'])}")
        print(f"Location: {self.root_path}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        downloader = YouTubePlaylistDownloader()
        downloader.run()
    except KeyboardInterrupt:
        print("\n\n⚠ Download interrupted by user")
        print("Progress has been saved. Run the script again to continue.")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
