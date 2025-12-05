import os
import unicodedata
from pathlib import Path
from mutagen.id3 import (
    ID3, ID3NoHeaderError,
    TALB, TPE1, TPE2, TIT2, TRCK, TPOS, TCON, TDRC, TSOA, APIC
)

# ------------------------
# CONFIGURATION
# ------------------------
ALBUM_ARTIST_DEFAULT = "Various Artists"
GENRE_DEFAULT = "Soundtrack"
YEAR_DEFAULT = "2024"
# ------------------------


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.split())


def clean_title(filename: str) -> str:
    """Strip numbering and weird characters from title."""
    title = Path(filename).stem
    while title and (title[0].isdigit() or title[0] in ".- "):
        title = title[1:]
    title = title.replace("_", " ").strip()
    return normalize(title)


def read_existing_artist_and_cover(filepath: str):
    """Extract original TPE1 + APIC frames."""
    artist = "Unknown Artist"
    covers = []

    try:
        audio = ID3(filepath)

        if "TPE1" in audio:
            artist = normalize(audio["TPE1"].text[0])

        for key in audio.keys():
            if key.startswith("APIC"):
                covers.append(audio[key])

    except:
        pass

    return artist, covers


def wipe_tags(filepath: str):
    """Remove all existing ID3 tags (v1 + v2)."""
    try:
        audio = ID3(filepath)
        audio.delete()
        audio.save()
    except ID3NoHeaderError:
        pass


def write_clean_tags(filepath: str, album: str, title: str, track_num: int, artist: str, covers):
    """Write clean ID3 tags."""
    audio = ID3()

    audio.add(TALB(encoding=3, text=album))                    # Album
    audio.add(TPE2(encoding=3, text=ALBUM_ARTIST_DEFAULT))     # Album Artist (grouping)
    audio.add(TPE1(encoding=3, text=artist))                   # Track Artist (preserved)
    audio.add(TIT2(encoding=3, text=title))                    # Title
    audio.add(TRCK(encoding=3, text=str(track_num)))           # Sequential Track Numbers
    audio.add(TPOS(encoding=3, text="1"))                      # Disc #
    audio.add(TSOA(encoding=3, text=album))                    # Album Sort

    if GENRE_DEFAULT:
        audio.add(TCON(encoding=3, text=GENRE_DEFAULT))

    if YEAR_DEFAULT:
        audio.add(TDRC(encoding=3, text=YEAR_DEFAULT))

    for cover in covers:
        audio.add(APIC(
            encoding=cover.encoding,
            mime=cover.mime,
            type=cover.type,
            desc=cover.desc,
            data=cover.data
        ))

    audio.save(filepath)


# ------------------------
# MAIN SCRIPT
# ------------------------
base_folder = input("Enter the full path to your music root folder: ").strip()

if not os.path.isdir(base_folder):
    print("Invalid folder path.")
    exit(1)

for root, dirs, files in os.walk(base_folder):
    mp3s = sorted([f for f in files if f.lower().endswith(".mp3")])

    if not mp3s:
        continue

    album_name = normalize(os.path.basename(root))
    print(f"\n=== Processing Album Folder: {album_name} ===")

    # Alphabetically ordered MP3 list = track order
    for index, mp3_file in enumerate(mp3s, start=1):
        full_path = os.path.join(root, mp3_file)
        print(f"→ Track {index}: {mp3_file}")

        # Extract track metadata to preserve
        artist, covers = read_existing_artist_and_cover(full_path)
        title = clean_title(mp3_file)

        # Remove all existing tags
        wipe_tags(full_path)

        # Write normalized tags with new track # (alphabetical)
        write_clean_tags(full_path, album_name, title, index, artist, covers)

print("\nAll albums processed successfully with alphabetic track ordering.")
