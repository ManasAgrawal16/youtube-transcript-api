from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import re
import os
import glob
import time
import random

app = FastAPI(title="YouTube Transcript Scraper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class TranscriptRequest(BaseModel):
    url: str
    language: str = "en"


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
    if re.match(r"^[0-9A-Za-z_-]{11}$", url_or_id.strip()):
        return url_or_id.strip()
    raise ValueError(f"Could not extract a valid YouTube video ID from: {url_or_id}")


def clean_vtt(vtt_content: str) -> str:
    lines = vtt_content.split("\n")
    cleaned = []
    seen = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        if line.startswith("NOTE"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line):
            continue
        if re.match(r"^\d+$", line):
            continue
        # Remove HTML tags
        line = re.sub(r"<[^>]+>", "", line)
        line = line.strip()
        # Skip duplicates
        if line and line not in seen:
            cleaned.append(line)
            seen.add(line)

    return " ".join(cleaned).strip()


def fetch_transcript(video_id: str, language: str = "en") -> str:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    output_path = f"/tmp/transcript_{video_id}"

    # Clean up old files
    for f in glob.glob(f"{output_path}*"):
        os.remove(f)

    # Random delay before each request — mimics human behaviour
    time.sleep(random.uniform(5, 10))

    ydl_opts = {
        "skip_download": True,
        "writeautomaticsub": True,
        "writesubtitles": True,
        "subtitlesformat": "vtt",
        "subtitleslangs": [language, "en"],
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        # These headers make yt-dlp look like a real browser
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        # Retry settings
        "retries": 3,
        "fragment_retries": 3,
        "sleep_interval": 3,
        "max_sleep_interval": 8,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        error_msg = str(e).lower()
        if "sign in" in error_msg or "bot" in error_msg or "429" in error_msg:
            raise Exception("YouTube is rate limiting this IP. Wait 30-60 minutes and try again.")
        if "subtitles" in error_msg or "caption" in error_msg:
            raise Exception("No captions available for this video.")
        raise Exception(f"yt-dlp error: {str(e)}")

    # Find downloaded VTT file
    vtt_files = glob.glob(f"{output_path}*.vtt")

    if not vtt_files:
        raise Exception("No transcript found. This video may not have captions enabled.")

    # Read and clean VTT
    with open(vtt_files[0], "r", encoding="utf-8") as f:
        vtt_content = f.read()

    # Cleanup temp files
    for f in vtt_files:
        os.remove(f)

    plain_text = clean_vtt(vtt_content)

    if not plain_text:
        raise Exception("Transcript was empty after processing.")

    return plain_text


@app.get("/")
def health_check():
    return {"status": "ok", "message": "YouTube Transcript Scraper (yt-dlp) is running"}


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
