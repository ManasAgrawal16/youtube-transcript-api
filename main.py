from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import re
import os
import glob

app = FastAPI(title="YouTube Transcript Scraper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
#  Request Body (for POST from n8n)
# ─────────────────────────────────────────────
class TranscriptRequest(BaseModel):
    url: str
    language: str = "en"


# ─────────────────────────────────────────────
#  Helper: Extract Video ID from any URL format
# ─────────────────────────────────────────────
def extract_video_id(url_or_id: str) -> str:
    patterns = [
        r"(?:v=)([0-9A-Za-z_-]{11})",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:embed\/)([0-9A-Za-z_-]{11})",
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    # If already a raw 11-char video ID
    if re.match(r"^[0-9A-Za-z_-]{11}$", url_or_id.strip()):
        return url_or_id.strip()

    raise ValueError(f"Could not extract a valid YouTube video ID from: {url_or_id}")


# ─────────────────────────────────────────────
#  Helper: Clean VTT subtitle file to plain text
# ─────────────────────────────────────────────
def clean_vtt(vtt_content: str) -> str:
    # Remove WEBVTT header
    lines = vtt_content.split("\n")
    cleaned = []
    seen = set()

    for line in lines:
        line = line.strip()

        # Skip empty lines, WEBVTT header, timestamps, NOTE lines
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        if line.startswith("NOTE"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line):  # timestamp line
            continue
        if re.match(r"^\d+$", line):  # sequence numbers
            continue

        # Remove HTML tags like <00:00:00.000>, <c>, </c>
        line = re.sub(r"<[^>]+>", "", line)

        # Remove duplicate consecutive lines (YouTube repeats lines in VTT)
        if line and line not in seen:
            cleaned.append(line)
            seen.add(line)

    return " ".join(cleaned).strip()


# ─────────────────────────────────────────────
#  Core: Fetch transcript using yt-dlp
# ─────────────────────────────────────────────
def fetch_transcript(video_id: str, language: str = "en") -> str:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    output_path = f"/tmp/transcript_{video_id}"

    # Clean up any old files first
    for f in glob.glob(f"{output_path}*"):
        os.remove(f)

    ydl_opts = {
        "skip_download": True,           # Don't download the video
        "writeautomaticsub": True,        # Get auto-generated subtitles
        "writesubtitles": True,           # Also get manual subtitles if available
        "subtitlesformat": "vtt",         # VTT format (easiest to parse)
        "subtitleslangs": [language, "en"],  # Try requested language, fallback to English
        "outtmpl": output_path,           # Output file path
        "quiet": True,                    # No console output
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        raise Exception(f"yt-dlp failed to fetch transcript: {str(e)}")

    # Find the downloaded VTT file
    vtt_files = glob.glob(f"{output_path}*.vtt")

    if not vtt_files:
        raise Exception("No transcript/subtitle file found. This video may not have captions.")

    # Read and clean the VTT file
    with open(vtt_files[0], "r", encoding="utf-8") as f:
        vtt_content = f.read()

    # Clean up temp files
    for f in vtt_files:
        os.remove(f)

    # Convert VTT to plain text
    plain_text = clean_vtt(vtt_content)

    if not plain_text:
        raise Exception("Transcript was empty after processing.")

    return plain_text


# ─────────────────────────────────────────────
#  Health Check
# ─────────────────────────────────────────────
@app.get("/")
def health_check():
    return {"status": "ok", "message": "YouTube Transcript Scraper (yt-dlp) is running"}


# ─────────────────────────────────────────────
#  GET /transcript — for browser & Postman testing
#  Usage: /transcript?url=https://youtube.com/watch?v=VIDEO_ID
#         /transcript?url=VIDEO_ID
# ─────────────────────────────────────────────
@app.get("/transcript")
def get_transcript_get(url: str, language: str = "en"):
    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        transcript_text = fetch_transcript(video_id, language)
        return {
            "success": True,
            "video_id": video_id,
            "language_requested": language,
            "transcript": transcript_text,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  POST /transcript — for n8n
#  Body: { "url": "https://youtube.com/...", "language": "en" }
# ─────────────────────────────────────────────
@app.post("/transcript")
def get_transcript_post(body: TranscriptRequest):
    try:
        video_id = extract_video_id(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        transcript_text = fetch_transcript(video_id, body.language)
        return {
            "success": True,
            "video_id": video_id,
            "language_requested": body.language,
            "transcript": transcript_text,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
