import gradio as gr
import subprocess
import os
import tempfile
from pathlib import Path
from faster_whisper import WhisperModel
from datetime import timedelta
import json

def format_timestamp(seconds):
    """Convert seconds to HH:MM:SS.mmm format"""
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:06.3f}"

def load_config():
    """Load optional user configuration from same directory as script"""
    script_dir = Path(__file__).parent
    config_path = script_dir / "transcribe_config.json"
    
    default_config = {
        "default_model": "tiny.en",
        "default_format": "md",
        "default_left_speaker": "",
        "default_right_speaker": ""
    }
    
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
            # Merge user config with defaults
            default_config.update(user_config)
            print(f"✓ Loaded config from: {config_path}")
        except Exception as e:
            print(f"⚠️ Warning: Could not load config file: {e}")
    
    return default_config

def check_audio_tracks(video_path):
    """Check how many audio tracks exist in the file"""
    result = subprocess.run([
        "ffmpeg", "-i", str(video_path)
    ], capture_output=True, text=True)
    
    # Count audio streams in ffmpeg output
    audio_count = result.stderr.count("Stream #0:") - result.stderr.count("Video:")
    return audio_count

def merge_dual_track_to_stereo(video_path, temp_dir):
    """
    Extract two mono audio tracks from MKV and combine into stereo
    Track 1 (0:a:0) -> Left channel
    Track 2 (0:a:1) -> Right channel
    Returns path to stereo audio file
    """
    track1_path = temp_dir / "track1.mp3"
    track2_path = temp_dir / "track2.mp3"
    stereo_output = temp_dir / "stereo_combined.mp3"
    
    # Extract Track 1 (mic/speaker A)
    result1 = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-map", "0:a:0",
        "-ac", "2",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(track1_path)
    ], capture_output=True, text=True)
    
    if result1.returncode != 0:
        raise RuntimeError(f"Error extracting Track 1: {result1.stderr}")
    
    # Extract Track 2 (meet/speaker B)
    result2 = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-map", "0:a:1",
        "-ac", "2",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(track2_path)
    ], capture_output=True, text=True)
    
    if result2.returncode != 0:
        raise RuntimeError(f"Error extracting Track 2: {result2.stderr}")
    
    # Combine: Track1 -> Left, Track2 -> Right
    result3 = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(track1_path),
        "-i", str(track2_path),
        "-filter_complex",
        "join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(stereo_output)
    ], capture_output=True, text=True)
    
    if result3.returncode != 0:
        raise RuntimeError(f"Error combining tracks: {result3.stderr}")
    
    return stereo_output

def process_stereo_audio(video_file, left_speaker_name, right_speaker_name,
                        output_filename, model_size="tiny.en", output_format="md"):
    if not video_file:
        return "❌ Error: No file selected", None, None, None
    
    try:
        # Validate and set speaker names
        left_name = left_speaker_name.strip() if left_speaker_name and left_speaker_name.strip() else "Speaker A (Left)"
        right_name = right_speaker_name.strip() if right_speaker_name and right_speaker_name.strip() else "Speaker B (Right)"
        
        # Get source file info
        source_path = Path(video_file)
        
        # Set output filename
        if not output_filename or output_filename.strip() == "":
            output_filename = source_path.stem + "_transcript"
        else:
            output_filename = Path(output_filename).stem
        
        # Setup paths - use cross-platform temp directory
        temp_dir = Path(tempfile.gettempdir()) / "transcribe"
        temp_dir.mkdir(exist_ok=True)
        
        left_channel = temp_dir / "left.wav"
        right_channel = temp_dir / "right.wav"
        
        # Set output file extension
        if output_format == "txt":
            output_file = temp_dir / f"{output_filename}.txt"
        elif output_format == "md":
            output_file = temp_dir / f"{output_filename}.md"
        elif output_format == "srt":
            output_file = temp_dir / f"{output_filename}.srt"
        else:
            output_file = temp_dir / f"{output_filename}.json"
        
        # Check if file has multiple audio tracks
        yield "🔍 Analyzing audio tracks...", None, None, None
        audio_track_count = check_audio_tracks(source_path)
        
        # Determine which file to process
        if audio_track_count >= 2:
            yield f"🎙️ Detected {audio_track_count} audio tracks - merging into stereo (Track 1→Left, Track 2→Right)...", None, None, None
            stereo_file = merge_dual_track_to_stereo(source_path, temp_dir)
            processing_file = stereo_file
        else:
            yield "🎙️ Detected single stereo track - processing directly...", None, None, None
            processing_file = source_path
        
        # Extract channels
        yield "🎬 Extracting left and right audio channels...", None, None, None
        
        # Extract left channel (channel 0)
        result_left = subprocess.run([
            "ffmpeg", "-i", str(processing_file),
            "-af", "pan=mono|c0=c0",
            "-ac", "1",
            str(left_channel),
            "-y"
        ], capture_output=True, text=True)
        
        if result_left.returncode != 0:
            yield f"❌ Error extracting left channel: {result_left.stderr}", None, None, None
            return
        
        # Extract right channel (channel 1)
        result_right = subprocess.run([
            "ffmpeg", "-i", str(processing_file),
            "-af", "pan=mono|c0=c1",
            "-ac", "1",
            str(right_channel),
            "-y"
        ], capture_output=True, text=True)
        
        if result_right.returncode != 0:
            yield f"❌ Error extracting right channel: {result_right.stderr}", None, None, None
            return
        
        yield f"🤖 Loading faster-whisper model (first run may take 2-3 minutes to download)...", None, None, None
        
        # Load faster-whisper model (CPU-optimized)
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8"
        )
        
        # Transcribe left channel
        yield f"🎤 Transcribing {left_name}...", None, None, None
        left_segments, left_info = model.transcribe(
            str(left_channel),
            language="en",
            beam_size=5
        )
        left_transcript = list(left_segments)
        
        # Transcribe right channel
        yield f"🎤 Transcribing {right_name}...", None, None, None
        right_segments, right_info = model.transcribe(
            str(right_channel),
            language="en",
            beam_size=5
        )
        right_transcript = list(right_segments)
        
        yield "📝 Merging transcripts...", None, None, None
        
        # Merge transcripts
        transcript = []
        for seg in left_transcript:
            transcript.append({
                "start": seg.start,
                "end": seg.end,
                "speaker": left_name,
                "channel": "left",
                "text": seg.text.strip()
            })
        
        for seg in right_transcript:
            transcript.append({
                "start": seg.start,
                "end": seg.end,
                "speaker": right_name,
                "channel": "right",
                "text": seg.text.strip()
            })
        
        # Sort by timestamp
        transcript.sort(key=lambda x: x["start"])
        
        # Detect and remove duplicates (when both channels have identical audio)
        # Check if left and right transcripts are very similar
        def are_transcripts_identical(left_trans, right_trans, threshold=0.8):
            """Check if two transcripts are mostly identical (mono audio saved as stereo)"""
            if len(left_trans) == 0 or len(right_trans) == 0:
                return False
            
            if abs(len(left_trans) - len(right_trans)) > 5:  # Allow small differences
                return False
            
            # Compare text content
            left_text = " ".join([seg.text.strip() for seg in left_trans])
            right_text = " ".join([seg.text.strip() for seg in right_trans])
            
            # Simple similarity check
            if left_text == right_text:
                return True
            
            # Check if substantial overlap exists
            similarity = len(set(left_text.split()) & set(right_text.split())) / len(set(left_text.split()) | set(right_text.split()))
            return similarity > threshold
        
        # Check for duplicate audio
        if are_transcripts_identical(left_transcript, right_transcript):
            yield "⚠️ Detected identical audio on both channels (mono file) - using single transcript...", None, None, None
            # Keep only left channel entries
            transcript = [t for t in transcript if t["channel"] == "left"]
            # Update speaker name to indicate it's mono
            for t in transcript:
                t["speaker"] = f"{left_name} (Mono)"
        
        # Remove the temporary 'channel' field
        for t in transcript:
            if "channel" in t:
                del t["channel"]
        
        # Generate outputs based on format
        if output_format == "txt":
            output_text = "\n\n".join([
                f"[{format_timestamp(t['start'])}] {t['speaker']}:\n{t['text']}"
                for t in transcript
            ])
            output_file.write_text(output_text, encoding='utf-8')
        
        elif output_format == "md":
            # Markdown format with timestamps every 5 minutes
            md_content = []
            last_timestamp_minute = -5  # Force first timestamp
            
            for t in transcript:
                current_minute = int(t['start'] / 60)
                # Add timestamp header every 5 minutes
                if current_minute - last_timestamp_minute >= 5:
                    timestamp_header = f"\n## {format_timestamp(t['start'])}\n\n"
                    md_content.append(timestamp_header)
                    last_timestamp_minute = current_minute
                
                # Format: **Speaker**: Dialog text
                md_content.append(f"**{t['speaker']}**: {t['text']}\n\n")
            
            output_file.write_text("".join(md_content), encoding='utf-8')
        
        elif output_format == "srt":
            srt_content = []
            for i, t in enumerate(transcript, 1):
                start_time = format_timestamp(t['start']).replace('.', ',')
                end_time = format_timestamp(t['end']).replace('.', ',')
                srt_content.append(f"{i}\n{start_time} --> {end_time}\n{t['speaker']}: {t['text']}\n")
            
            output_file.write_text("\n".join(srt_content), encoding='utf-8')
        
        elif output_format == "json":
            json_data = {
                "source_file": source_path.name,
                "model": model_size,
                "audio_tracks_detected": audio_track_count,
                "speakers": {
                    "left_channel": left_name,
                    "right_channel": right_name
                },
                "transcript": transcript
            }
            output_file.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding='utf-8')
        
        # Create preview (first 10 entries)
        preview = "\n\n".join([
            f"[{format_timestamp(t['start'])}] {t['speaker']}:\n{t['text']}"
            for t in transcript[:10]
        ])
        
        if len(transcript) > 10:
            preview += f"\n\n... ({len(transcript) - 10} more entries) ..."
        
        # Cleanup temp files
        left_channel.unlink(missing_ok=True)
        right_channel.unlink(missing_ok=True)
        if audio_track_count >= 2:
            stereo_file.unlink(missing_ok=True)
        
        track_info = f" (merged from {audio_track_count} tracks)" if audio_track_count >= 2 else ""
        success_msg = f"""✅ TRANSCRIPTION COMPLETE!

📊 Total segments: {len(transcript)}
🎤 Speakers: {left_name} | {right_name}{track_info}

⚠️ IMPORTANT: Click the "⬇️ Download Transcript" button below to save your file!
The transcript will be saved to your browser's default download location."""
        
        yield success_msg, preview, str(output_file), str(output_file)
        
    except Exception as e:
        yield f"❌ Error: {str(e)}", None, None, None

# Load user configuration
config = load_config()

# Gradio interface with enhanced UX
with gr.Blocks(title="Stereo Channel Transcription") as demo:
    gr.Markdown("""
# 🎙️ Stereo Channel Transcription

**Supports two input types:**
- **Dual-track MKV** (e.g., OBS recordings): Automatically merges Track 1→Left, Track 2→Right
- **Single stereo file** (MKV/MP4/WAV): Processes left/right channels directly
""")
    
    with gr.Row():
        with gr.Column():
            video_input = gr.File(
                label="📂 Select Audio/Video File",
                file_types=[".mkv", ".mp4", ".avi", ".mov", ".wav", ".mp3"],
                type="filepath"
            )
            
            gr.Markdown("### 🎤 Speaker Names")
            with gr.Row():
                left_speaker = gr.Textbox(
                    label="👤 Left Channel Speaker",
                    placeholder="e.g., John Smith, Interviewer, Microphone",
                    info="Name for the speaker on the left audio channel (or Track 1)",
                    value=config.get("default_left_speaker", "")
                )
                
                right_speaker = gr.Textbox(
                    label="👤 Right Channel Speaker",
                    placeholder="e.g., Jane Doe, Guest, Meeting Audio",
                    info="Name for the speaker on the right audio channel (or Track 2)",
                    value=config.get("default_right_speaker", "")
                )
            
            output_name = gr.Textbox(
                label="💾 Output Filename (without extension)",
                placeholder="Leave blank to use source filename + '_transcript'",
                info="File will be available for download after processing"
            )
            
            with gr.Row():
                model_dropdown = gr.Dropdown(
                    choices=["tiny.en", "base.en", "small.en", "medium.en", "large-v2"],
                    value=config.get("default_model", "tiny.en"),
                    label="🤖 Model Size",
                    info="Tiny = 10x faster. Medium = best balance. Large = most accurate but slower."
                )
                
                format_dropdown = gr.Dropdown(
                    choices=["md", "txt", "srt", "json"],
                    value=config.get("default_format", "md"),
                    label="📄 Output Format",
                    info="MD = markdown (default), TXT = timestamped, SRT = subtitles, JSON = data"
                )
            
            process_btn = gr.Button("🚀 Start Transcription", variant="primary", size="lg")
            
            download_button = gr.File(
                label="⬇️ Download Transcript (available after processing completes)",
                interactive=False,
                visible=True
            )
            
            clear_btn = gr.Button("🔄 Clear and Start New Transcription", size="lg")
        
        with gr.Column():
            status_output = gr.Textbox(
                label="📊 Status",
                lines=8,
                interactive=False
            )
            
            preview_output = gr.Textbox(
                label="👀 Preview (First 10 segments)",
                lines=18,
                interactive=False
            )
            
            file_output = gr.Textbox(
                label="📁 Internal Path",
                interactive=False,
                visible=False
            )
    
    gr.Markdown("""
---
### 🎙️ How It Works

**Dual-Track Files (OBS recordings):**
- Automatically detects multiple audio tracks
- Merges Track 1 (mic) to LEFT channel, Track 2 (meeting/desktop) to RIGHT channel
- Then transcribes each channel separately

**Single Stereo Files:**
- Processes LEFT and RIGHT channels directly

### ⚠️ File Download Instructions

After transcription completes:
1. ✅ Click the **"⬇️ Download Transcript"** button (below Start button)
2. ✅ File saves to your browser's default download location
3. ✅ Move it from Downloads to wherever you need it

---

### ⚙️ Performance Notes

- **First run**: Model downloads automatically (~39MB for tiny.en, ~200MB for medium, ~1.5GB for large-v2)
- **Processing time**: ~1-2 seconds per minute of audio with tiny.en on Intel CPU (4-5x faster than WhisperX!)
- **Supported formats**: MKV, MP4, AVI, MOV, WAV, MP3

### 💡 Tips

- **Markdown (MD)**: Clean format with timestamps every 5 minutes, bold speaker names
- Use **tiny.en** model for fastest processing (10x faster than large, good accuracy)
- Use **medium.en** model for best accuracy/speed balance
- Use **small.en** model for faster processing (3x speed vs medium, slight quality loss)
- SRT format works great for video editors
- JSON format preserves all metadata

### ⚙️ Configuration File (Optional)

- Create a `transcribe_config.json` file in the same folder as this script to set defaults
- Copy `transcribe_config.example.json` as a starting point
- Available options: `default_model`, `default_format`, `default_left_speaker`, `default_right_speaker`
- Changes take effect when you restart the application
- Example config:
```json
{
    "default_model": "tiny.en",
    "default_format": "md",
    "default_left_speaker": "Interviewer",
    "default_right_speaker": "Guest"
}

""")

    # Event handlers
    process_btn.click(
    fn=process_stereo_audio,
    inputs=[video_input, left_speaker, right_speaker, output_name, model_dropdown, format_dropdown],
    outputs=[status_output, preview_output, file_output, download_button]
    )

    # Clear button resets everything
    clear_btn.click(
    fn=lambda: (None, "", "", "", "tiny.en", "md", "", "", None, None),
    inputs=[],
    outputs=[video_input, left_speaker, right_speaker, output_name, model_dropdown, format_dropdown, status_output, preview_output, file_output, download_button]
    )

demo.launch(server_name="0.0.0.0", server_port=7860)


