import streamlit as st
import time
import subprocess
import os
import shutil
from pathlib import Path
from datetime import datetime

from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine
from src.WhisperLyricsEngine import WhisperLyricsEngine

# --- Streamlit Page Config ---
st.set_page_config(
    page_title="YT Music Sync",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom Styling ---
st.markdown(
    """
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    .playlist-card {
        background-color: #161b22;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #30363d;
        margin-bottom: 15px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .playlist-card:hover {
        border-color: #58a6ff;
        transform: translateY(-2px);
    }
    .status-badge {
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    .status-completed { background-color: #238636; color: white; }
    .status-pending { background-color: #af8500; color: white; }
    .status-failed { background-color: #da3633; color: white; }
    </style>
""",
    unsafe_allow_html=True,
)


# --- Helper Functions ---
def get_ytdlp_version(path):
    try:
        res = subprocess.run(
            [path, "--version"], capture_output=True, text=True, shell=False
        )
        return res.stdout.strip()
    except Exception:
        return "Not found"


def get_disk_usage(path):
    try:
        total, used, free = shutil.disk_usage(path)
        return f"{used // (2**30)}GB / {total // (2**30)}GB"
    except Exception:
        return "Unknown"


@st.cache_resource
def init_engines():
    """Initializes components once to handle state effectively."""
    try:
        config = ConfigManager()
        state = StateManager()
        resolver = PlaylistResolver(config, state)
        engine = DownloadEngine(config)
        lyrics = WhisperLyricsEngine()
        return config, state, resolver, engine, lyrics
    except Exception as e:
        st.error(f"Initialization Error: {e}")
        return None, None, None, None, None


def run_sync(p, config, state, engine, lyrics_engine):
    """Encapsulated sync logic for robustness."""
    with st.status(f"Syncing: {p['title']}", expanded=True) as status:
        status.write("📡 Fetching updates from YouTube...")
        success = engine.download(p)

        if not success:
            status.update(label=f"❌ Failed: {p['title']}", state="error")
            return False

        # Lyrics Step
        playlist_dir = config.root_path / engine.clean_filename(p["title"])
        status.write("🎤 Checking for missing lyrics...")

        audio_files = list(playlist_dir.glob("*.opus"))
        for audio_file in audio_files:
            lrc_file = audio_file.with_suffix(".lrc")
            if not lrc_file.exists():
                status.write(f"Transcribing: {audio_file.name}")
                try:
                    lyrics_engine.generate_lrc(audio_file)
                except Exception as e:
                    status.write(f"⚠️ Failed lyrics for {audio_file.name}: {e}")

        state.mark_completed(p["id"])
        status.update(label=f"✅ Completed: {p['title']}", state="complete")
        return True


# --- Main App ---
def main():
    config, state, resolver, engine, lyrics = init_engines()
    if not config:
        return

    # --- Sidebar ---
    with st.sidebar:
        st.title("🎵 YT Sync")
        st.subheader("System Status")
        st.write(f"**yt-dlp:** `{get_ytdlp_version(config.ytdlp_path)}`")
        st.write(f"**Storage:** `{get_disk_usage(config.root_path)}`")
        st.write(f"**OS:** `{config.os_type.upper()}`")

        st.divider()

        if st.button("🚀 Sync All Pending", use_container_width=True, type="primary"):
            st.session_state.sync_all = True

        if st.button("🗑️ Clear Download State", use_container_width=True):
            if os.path.exists("download_state.json"):
                os.remove("download_state.json")
                st.toast("Cache cleared! Reloading...")
                time.sleep(1)
                st.rerun()

    # --- Header & Stats ---
    st.title("Playlist Synchronization")

    with st.spinner("Resolving playlists..."):
        if config.input_method == "channel":
            playlists = resolver.from_channel()
        elif config.input_method == "playlist_file":
            playlists = resolver.from_file()
        else:
            playlists = [
                resolver.get_playlist_info(url) for url in config.playlist_urls
            ]

    playlists = [p for p in playlists if p]
    completed_ids = [p["id"] for p in playlists if state.is_completed(p["id"])]
    pending = [p for p in playlists if p["id"] not in completed_ids]

    c1, c2, c3 = st.columns(3)
    c1.metric("Tracked Playlists", len(playlists))
    c2.metric("Up to Date", len(completed_ids))
    c3.metric(
        "Updates Needed",
        len(pending),
        delta=len(pending),
        delta_color="inverse" if pending else "normal",
    )

    # --- Tabs ---
    tab_overview, tab_settings = st.tabs(["📊 Overview", "⚙️ Configuration"])

    with tab_overview:
        search = st.text_input(
            "🔍 Filter Playlists",
            placeholder="Enter playlist title...",
            label_visibility="collapsed",
        )

        # Grid layout for cards
        cols = st.columns(2)
        for i, p in enumerate(playlists):
            if search and search.lower() not in p["title"].lower():
                continue

            is_done = p["id"] in completed_ids
            col_idx = i % 2

            with cols[col_idx]:
                st.markdown(
                    f"""
                <div class="playlist-card">
                    <span class="status-badge status-{'completed' if is_done else 'pending'}">
                        {'Up to Date' if is_done else 'Pending'}
                    </span>
                    <h3 style="margin: 10px 0;">{p['title']}</h3>
                    <code style="font-size: 0.75rem;">{p['id']}</code>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                btn_col, link_col = st.columns([1, 1])
                if btn_col.button(
                    "Sync Now", key=f"btn_{p['id']}", use_container_width=True
                ):
                    run_sync(p, config, state, engine, lyrics)
                    st.rerun()

                link_col.link_button(
                    "View on YouTube", p["url"], use_container_width=True
                )
                st.write("")  # Spacer

    with tab_settings:
        st.subheader("Project Configuration")
        st.write("Current settings loaded from `config.yml`")
        st.json(config.data)

        st.subheader("Internal State")
        st.write("Tracking `download_state.json` data")
        st.json(state.state)

    # --- Background Logic ---
    if st.session_state.get("sync_all", False):
        st.session_state.sync_all = False
        if not pending:
            st.toast("Nothing to sync!", icon="ℹ️")
        else:
            for p in pending:
                run_sync(p, config, state, engine, lyrics)
            st.success("All playlists synced!")
            time.sleep(1)
            st.rerun()


if __name__ == "__main__":
    main()
