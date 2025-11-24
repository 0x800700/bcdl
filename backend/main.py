from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import uuid
from core import BandcampScraper
import logging

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scraper = BandcampScraper()

# In-memory state for jobs
jobs = {}

class ScanRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    urls: List[str]
    format: str = "FLAC"

class JobStatus(BaseModel):
    id: str
    type: str
    status: str
    progress: List[str]
    result: Optional[dict] = None

@app.post("/api/scan")
async def scan(request: ScanRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "type": "scan",
        "status": "running",
        "progress": [],
        "result": None
    }
    background_tasks.add_task(run_scan, job_id, request.url)
    return {"job_id": job_id}

@app.post("/api/download")
async def download(request: DownloadRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "type": "download",
        "status": "running",
        "progress": [],
        "result": {"downloaded": 0, "failed": 0, "skipped": 0}
    }
    background_tasks.add_task(run_download, job_id, request.urls, request.format)
    return {"job_id": job_id}

@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

def run_scan(job_id, url):
    try:
        jobs[job_id]["progress"].append(f"Scanning {url}...")
        jobs[job_id]["result"] = [] # Initialize empty list
        
        def on_album(album):
            jobs[job_id]["result"].append(album)
            
        albums = scraper.scan_artist(url, on_album_found=on_album)
        # Result is already populated by callback, but ensure final consistency
        jobs[job_id]["result"] = albums 
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"].append(f"Found {len(albums)} albums.")
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"].append(f"Error: {str(e)}")

def run_download(job_id, urls, format):
    try:
        total = len(urls)
        for i, url in enumerate(urls):
            jobs[job_id]["progress"].append(f"[{i+1}/{total}] Processing {url}...")
            
            def update_progress(msg):
                jobs[job_id]["progress"].append(msg)
                # Keep log size manageable
                if len(jobs[job_id]["progress"]) > 50:
                    jobs[job_id]["progress"].pop(0)

            result = scraper.download_album(url, target_format=format, progress_callback=update_progress)
            
            if result == "downloaded":
                jobs[job_id]["result"]["downloaded"] += 1
            elif result == "failed":
                jobs[job_id]["result"]["failed"] += 1
            else:
                jobs[job_id]["result"]["skipped"] += 1
                
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"].append("All downloads finished.")
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"].append(f"Critical Error: {str(e)}")
