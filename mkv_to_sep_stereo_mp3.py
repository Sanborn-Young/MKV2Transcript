import os
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox

# Adjust if ffmpeg is not on PATH
FFMPEG_BIN = "ffmpeg"


def run_ffmpeg(cmd_args):
    """Run ffmpeg command and raise on error."""
    result = subprocess.run(
        [FFMPEG_BIN] + cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error:\n{result.stderr}")
    return result


def main():
    root = tk.Tk()
    root.withdraw()  # hide main window

    # 1) Ask user to pick the MKV file
    mkv_path = filedialog.askopenfilename(
        title="Select MKV file recorded from OBS",
        filetypes=[("MKV files", "*.mkv"), ("All files", "*.*")]
    )
    if not mkv_path:
        return  # user cancelled

    mkv_dir = os.path.dirname(mkv_path)
    mkv_base = os.path.splitext(os.path.basename(mkv_path))[0]

    # 2) Ask for final combined MP3 name (default: same base name + _combined.mp3)
    default_output_name = f"{mkv_base}_combined.mp3"
    output_name = simpledialog.askstring(
        "Output file name",
        "Enter final stereo MP3 file name:",
        initialvalue=default_output_name,
        parent=root
    )
    if not output_name:
        return  # user cancelled

    # Enforce .mp3 extension
    if not output_name.lower().endswith(".mp3"):
        output_name += ".mp3"

    output_path = os.path.join(mkv_dir, output_name)

    try:
        # 3) Create temporary directory for intermediate MP3s
        with tempfile.TemporaryDirectory() as tmpdir:
            mic_mp3 = os.path.join(tmpdir, "mic_tmp.mp3")
            meet_mp3 = os.path.join(tmpdir, "meet_tmp.mp3")

            # 3a) Extract Track 1 (mic) to mic_tmp.mp3
            # 0:a:0 = first audio stream from MKV (Track 1)
            run_ffmpeg([
                "-y",
                "-i", mkv_path,
                "-map", "0:a:0",
                "-ac", "2",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                mic_mp3
            ])

            # 3b) Extract Track 2 (Meet) to meet_tmp.mp3
            # 0:a:1 = second audio stream from MKV (Track 2)
            run_ffmpeg([
                "-y",
                "-i", mkv_path,
                "-map", "0:a:1",
                "-ac", "2",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                meet_mp3
            ])

            # 4) Combine them into one stereo MP3
            # mic = left, meet = right
            run_ffmpeg([
                "-y",
                "-i", mic_mp3,
                "-i", meet_mp3,
                "-filter_complex",
                "join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                output_path
            ])

        messagebox.showinfo(
            "Done",
            f"Created stereo MP3:\n{output_path}"
        )

    except Exception as e:
        messagebox.showerror("Error", str(e))
        # Also print to stderr for debugging when run from console
        print(e, file=sys.stderr)


if __name__ == "__main__":
    main()
