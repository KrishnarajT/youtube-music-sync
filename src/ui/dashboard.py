import streamlit as st
import time
import subprocess
import os
from pathlib import Path

# Importing your refactored classes from the src directory
from src.ConfigManager import ConfigManager
from src.StateManager import StateManager
from src.PlaylistResolver import PlaylistResolver
from src.DownloadEngine import DownloadEngine

# --- Streamlit Page Config ---
st.set_page_config(
    page_title="YT Music Sync Dashboard",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_ytdlp_version(path):
    """Retrieves the current version of the yt-dlp executable."""
    try:
        # Use shell=True for Windows compatibility as established in previous fixes
        res = subprocess.run(
            [path, "--version"], capture_output=True, text=True, shell=True
        )
        return res.stdout.strip()
    except Exception:
        return "Not found"


def main():
    st.title("🎵 YouTube Music Sync Dashboard")

    # Initialize Core Components
    # These are initialized once per session/refresh
    try:
        config = ConfigManager()
        state = StateManager()
        resolver = PlaylistResolver(config, state)
        engine = DownloadEngine(config)
    except Exception as e:
        st.error(f"Failed to initialize components: {e}")
        return

    # --- Sidebar: System Info ---
    with st.sidebar:
        st.header("⚙️ System Status")
        ytdlp_ver = get_ytdlp_version(config.ytdlp_path)

        st.metric("yt-dlp version", ytdlp_ver)
        st.write(f"**OS Type:** `{config.os_type.capitalize()}`")
        st.write(f"**Root Path:** `{config.root_path}`")

        st.divider()
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()

    # --- Main Content Area ---
    tab_progress, tab_logs, tab_settings = st.tabs(
        ["📊 Progress", "📝 Activity Logs", "⚙️ Config & State"]
    )

    with tab_progress:
        # Resolve Target Playlists based on Config
        with st.spinner("Loading playlist metadata..."):
            if config.input_method == "channel":
                playlists = resolver.from_channel()
            elif config.input_method == "playlist_file":
                # Fallback to resolver's internal logic for files
                playlists = resolver.from_file()
            else:
                playlists = [
                    resolver.get_playlist_info(url) for url in config.playlist_urls
                ]

        # Filter valid entries
        playlists = [p for p in playlists if p]

        if not playlists:
            st.warning("No playlists found based on your current configuration.")
            return

        # Metrics Row
        completed_list = [p for p in playlists if state.is_completed(p["id"])]
        pending_list = [p for p in playlists if not state.is_completed(p["id"])]

        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Total", len(playlists))
        m_col2.metric(
            "Completed", len(completed_list), delta=f"{len(completed_list)} done"
        )
        m_col3.metric(
            "Pending",
            len(pending_list),
            delta=f"-{len(pending_list)}",
            delta_color="inverse",
        )

        # Global Progress Bar
        progress_val = len(completed_list) / len(playlists) if playlists else 0
        st.progress(
            progress_val, text=f"Overall Collection Sync: {int(progress_val*100)}%"
        )

        st.divider()

        # Playlist Grid/List
        st.subheader("Playlist Catalog")

        # Search/Filter Bar
        search_query = st.text_input("🔍 Search playlists by name...", "")

        for p in playlists:
            # Simple filtering
            if search_query.lower() not in p["title"].lower():
                continue

            is_done = state.is_completed(p["id"])
            status_label = "✅ COMPLETED" if is_done else "⏳ PENDING"

            with st.expander(f"{status_label} | {p['title']}"):
                col_info, col_action = st.columns([3, 1])

                with col_info:
                    st.write(f"**Playlist ID:** `{p['id']}`")
                    st.write(f"**Source URL:** [View on YouTube]({p['url']})")

                with col_action:
                    # Individual sync button
                    btn_label = "Re-sync" if is_done else "Start Sync"
                    if st.button(
                        btn_label, key=f"sync_{p['id']}", use_container_width=True
                    ):

                        log_placeholder = st.empty()
                        with st.status(
                            f"Syncing: {p['title']}...", expanded=True
                        ) as status:
                            # Direct call to engine.download logic but with UI feedback
                            # We can capture the output by running a similar command
                            success = engine.download(p)

                            if success:
                                state.mark_completed(p["id"])
                                status.update(
                                    label="Sync Successful!", state="complete"
                                )
                                st.toast(f"Finished {p['title']}", icon="✅")
                                time.sleep(1)
                                st.rerun()
                            else:
                                status.update(label="Sync Failed", state="error")
                                st.error(f"Error occurred while syncing {p['title']}")

    with tab_logs:
        st.subheader("Real-time Output")
        st.info("Manual sync logs will appear here during execution.")
        # Note: True global background logging would require a separate thread/queue system.
        # This tab is currently a placeholder for future session-wide logging.

    with tab_settings:
        col_c, col_s = st.columns(2)
        with col_c:
            st.subheader("Current Config (`config.yml`)")
            st.json(config.data)
        with col_s:
            st.subheader("State Data (`download_state.json`)")
            st.json(state.state)


if __name__ == "__main__":
    main()
