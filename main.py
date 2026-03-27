from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    VideoUnavailable,
    TranscriptsDisabled,
)
import re

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

def fetch_transcript(video_id: str, language: str) -> str:
    ytt = YouTubeTranscriptApi()
    transcript_list = ytt.list(video_id)
    try:
        transcript = transcript_list.find_transcript([language])
    except NoTranscriptFound:
        transcript = next(iter(transcript_list))
    fetched = transcript.fetch()
    full_text = " ".join([segment.text for segment in fetched])
    return full_text

@app.get("/")
def health_check():
    return {"status": "ok", "message": "YouTube Transcript Scraper is running"}

@app.get("/transcript")
def get_transcript_get(url: str, language: str = "en"):
    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        transcript_text = fetch_transcript(video_id, language)
        return {"success": True, "video_id": video_id, "language_requested": language, "transcript": transcript_text}
    except VideoUnavailable:
        raise HTTPException(status_code=404, detail="Video is unavailable or private.")
    except TranscriptsDisabled:
        raise HTTPException(status_code=403, detail="Transcripts are disabled for this video.")
    except NoTranscriptFound:
        raise HTTPException(status_code=404, detail="No transcript found for this video.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.post("/transcript")
def get_transcript_post(body: TranscriptRequest):
    try:
        video_id = extract_video_id(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        transcript_text = fetch_transcript(video_id, body.language)
        return {"success": True, "video_id": video_id, "language_requested": body.language, "transcript": transcript_text}
    except VideoUnavailable:
        raise HTTPException(status_code=404, detail="Video is unavailable or private.")
    except TranscriptsDisabled:
        raise HTTPException(status_code=403, detail="Transcripts are disabled for this video.")
    except NoTranscriptFound:
        raise HTTPException(status_code=404, detail="No transcript found for this video.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
