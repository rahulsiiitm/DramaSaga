import os
import requests

from .. import config
from ..retry import call_with_retries
from .nvidia import get_key

MAGPIE_BASE = "https://877104f7-e885-42b9-8de8-f6e4c6303969.invocation.api.nvcf.nvidia.com"

def list_voices():
    if config.DRY_RUN:
        return {"voices": ["Magpie-Multilingual.EN-US.Aria", "Magpie-Multilingual.EN-US.Jason"]}
    key = get_key("NVIDIA_KEY")
    assert key, "NVIDIA_KEY missing"
    r = call_with_retries(lambda: requests.get(f"{MAGPIE_BASE}/v1/audio/list_voices",
                                               headers={"Authorization": f"Bearer {key}"}, timeout=60))
    r.raise_for_status()
    return r.json()

def synthesize(text, voice, out_path, language="en-US", sample_rate=44100):
    out_path = __import__("pathlib").Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if config.DRY_RUN:
        import wave, struct, math
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            frames = int(sample_rate * 0.4)
            w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 220 * i / sample_rate))) for i in range(frames)))
        return {"path": str(out_path), "dry": True}
    key = get_key("NVIDIA_KEY")
    assert key, "NVIDIA_KEY missing"
    data = {"text": text, "language": language, "voice": voice, "encoding": "LINEAR_PCM", "sample_rate_hz": str(sample_rate)}
    r = call_with_retries(lambda: requests.post(f"{MAGPIE_BASE}/v1/audio/synthesize",
                                                headers={"Authorization": f"Bearer {key}"}, data=data, timeout=180))
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    return {"path": str(out_path), "bytes": len(r.content)}

