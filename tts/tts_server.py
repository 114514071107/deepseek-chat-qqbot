#!/usr/bin/env python3
"""GPT-SoVITS TTS HTTP server for dsh-qq-bridge.

Loads the pretrained v2Pro base models once at startup and exposes:
  POST /tts
    {
      "text": "要合成的文本",
      "ref_audio": "/path/to/ref.wav",  // optional
      "ref_text": "参考音频的文本",      // optional
      "language": "Chinese",             // optional
      "format": "mp3"                    // mp3 or wav
    }
Returns the synthesized audio file.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import asynccontextmanager

import soundfile as sf
import torch
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
GS_PATH = os.path.dirname(os.path.abspath(__file__))
GS_GPT_PATH = os.path.join(GS_PATH, "GPT_SoVITS")
os.chdir(GS_PATH)
sys.path.insert(0, GS_GPT_PATH)
sys.path.insert(0, GS_PATH)

from GPT_SoVITS.inference_webui import (  # noqa: E402
    change_gpt_weights,
    change_sovits_weights,
    get_tts_wav,
)

# ---------------------------------------------------------------------------
# Config (using v2 final GPT + v2Pro SoVITS as the recommended base combo)
# ---------------------------------------------------------------------------
DEFAULT_GPT = os.environ.get(
    "GS_GPT_PATH",
    os.path.join(
        GS_PATH,
        "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
    ),
)
DEFAULT_SOVITS = os.environ.get(
    "GS_SOVITS_PATH",
    os.path.join(
        GS_PATH,
        "GPT_SoVITS/pretrained_models/v2Pro/s2Dv2Pro.pth",
    ),
)
DEFAULT_REF_AUDIO = os.environ.get("GS_REF_AUDIO", os.path.join(GS_PATH, "default_ref.wav"))
DEFAULT_REF_TEXT = os.environ.get(
    "GS_REF_TEXT", "这是一段默认参考音频，请替换成目标说话人的声音样本。"
)
DEFAULT_LANGUAGE = os.environ.get("GS_LANGUAGE", "Chinese")

# Global state filled during startup
MODEL_STATE = {
    "loaded": False,
    "gpt_path": None,
    "sovits_path": None,
    "error": None,
}


def _load_models(gpt_path: str, sovits_path: str):
    print(f"[TTS Server] Loading SoVITS weights from {sovits_path}", flush=True)
    change_sovits_weights(sovits_path=sovits_path)
    print(f"[TTS Server] Loading GPT weights from {gpt_path}", flush=True)
    change_gpt_weights(gpt_path=gpt_path)
    print("[TTS Server] Models loaded.", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _load_models(DEFAULT_GPT, DEFAULT_SOVITS)
        MODEL_STATE["loaded"] = True
        MODEL_STATE["gpt_path"] = DEFAULT_GPT
        MODEL_STATE["sovits_path"] = DEFAULT_SOVITS
    except Exception as e:
        MODEL_STATE["error"] = str(e)
        print(f"[TTS Server] Failed to load models: {e}", flush=True)
    yield
    print("[TTS Server] Shutting down.", flush=True)


app = FastAPI(title="GPT-SoVITS TTS Server", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "ok": MODEL_STATE["loaded"],
        "error": MODEL_STATE["error"],
        "cuda": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    }


@app.api_route("/tts", methods=["GET", "POST"])
async def tts(req: Request):
    if not MODEL_STATE["loaded"]:
        return JSONResponse(
            status_code=503,
            content={"error": "Models not loaded", "detail": MODEL_STATE["error"]},
        )

    if req.method == "GET":
        data = dict(req.query_params)
    else:
        data = await req.json()
    text = data.get("text", "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "text is required"})

    ref_audio = data.get("ref_audio", DEFAULT_REF_AUDIO) or DEFAULT_REF_AUDIO
    ref_text = data.get("ref_text", DEFAULT_REF_TEXT) or DEFAULT_REF_TEXT
    language = data.get("language", DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE
    output_format = (data.get("format", "mp3") or "mp3").lower()

    if not os.path.isfile(ref_audio):
        return JSONResponse(
            status_code=400,
            content={"error": f"reference audio not found: {ref_audio}"},
        )

    start = time.time()
    print(f"[TTS Server] Synthesizing: {text[:60]}...", flush=True)

    try:
        gen = get_tts_wav(
            ref_wav_path=ref_audio,
            prompt_text=ref_text,
            prompt_language=language,
            text=text,
            text_language=language,
            top_k=data.get("top_k", 20),
            top_p=data.get("top_p", 0.6),
            temperature=data.get("temperature", 0.6),
            speed=data.get("speed", 1.0),
        )
        result = list(gen)
        if not result:
            raise RuntimeError("empty synthesis result")
        sr, audio = result[-1]
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"synthesis failed: {e}"})

    # Save temporary WAV
    fd, wav_path = tempfile.mkstemp(prefix="gs_tts_", suffix=".wav")
    os.close(fd)
    sf.write(wav_path, audio, sr)

    if output_format == "wav":
        return FileResponse(wav_path, media_type="audio/wav", filename="voice.wav")

    # Convert to MP3 with ffmpeg
    fd2, mp3_path = tempfile.mkstemp(prefix="gs_tts_", suffix=".mp3")
    os.close(fd2)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                wav_path,
                "-ar",
                "32000",
                "-ac",
                "1",
                "-b:a",
                "128k",
                mp3_path,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        os.remove(wav_path)
        os.remove(mp3_path)
        return JSONResponse(
            status_code=500,
            content={"error": f"ffmpeg mp3 conversion failed: {e.stderr.decode('utf-8', errors='ignore')}"},
        )

    os.remove(wav_path)
    print(f"[TTS Server] Done in {time.time() - start:.2f}s -> {mp3_path}", flush=True)
    return FileResponse(mp3_path, media_type="audio/mpeg", filename="voice.mp3")


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("TTS_HOST", "0.0.0.0")
    port = int(os.environ.get("TTS_PORT", "18765"))
    uvicorn.run(app, host=host, port=port, log_level="info")
