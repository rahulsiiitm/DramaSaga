import os
import requests

from .. import config
from ..retry import call_with_retries

def get_key(name):
    try:
        from google.colab import userdata
        return userdata.get(name)
    except Exception:
        return os.environ.get(name)

def nvidia_chat(model, messages, max_tokens=2000, temperature=0.7, reasoning=None):
    if config.DRY_RUN:
        return {"dry": True, "model": model, "messages": messages}
    key = get_key("NVIDIA_KEY")
    assert key, "NVIDIA_KEY missing"
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "stream": True}
    if reasoning == "off":
        body["chat_template_kwargs"] = {"enable_thinking": False}
    elif reasoning:
        body["reasoning_effort"] = reasoning
    wall_clock = max(150, int(max_tokens / 24 * 1.5))
    import json as _json, time as _time
    from ..retry import RETRYABLE_STATUS, RetryableStatusError

    import signal as _sig

    class _HardDeadline(Exception):
        pass

    def _alarm(_signum, _frame):
        raise _HardDeadline("hard deadline")

    def _call():
        print(f"[nvidia] {model} attempt start max_tokens={max_tokens} wall={wall_clock}s", flush=True)
        _sig.signal(_sig.SIGALRM, _alarm)
        _sig.alarm(wall_clock + 90)
        try:
            return _call_inner()
        finally:
            _sig.alarm(0)

    def _call_inner():
        r = requests.post(
            f"{config.NVIDIA_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=(30, 60),
            stream=True,
        )
        if r.status_code in RETRYABLE_STATUS:
            r.close()
            raise RetryableStatusError(f"retryable status {r.status_code}", response=r)
        r.raise_for_status()
        content, reasoning_text = [], []
        start = _time.time()
        try:
            buf = ""
            for raw in r.iter_content(chunk_size=1, decode_unicode=True):
                if _time.time() - start > wall_clock:
                    print(f"[nvidia] {model} wall-clock kill at {wall_clock}s", flush=True)
                    raise requests.Timeout(f"stream exceeded wall clock {wall_clock}s")
                if not raw:
                    continue
                buf += raw
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = _json.loads(data)
                    if not chunk.get("choices"):
                        continue
                    delta = chunk["choices"][0].get("delta", {})
                    if delta.get("content"):
                        content.append(delta["content"])
                    if delta.get("reasoning_content"):
                        reasoning_text.append(delta["reasoning_content"])
        finally:
            r.close()
        return {"choices": [{"message": {"content": "".join(content),
                                         "reasoning_content": "".join(reasoning_text)}}],
                "usage": {"streamed": True, "wall_s": round(_time.time() - start, 1)}}

    return call_with_retries(_call)

def message_text(response_json):
    m = response_json["choices"][0]["message"]
    return m.get("content") or m.get("reasoning_content") or ""

