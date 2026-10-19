import json, os, pathlib, time
import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = os.environ.get("MD_CLAUDE_MODEL", "claude-sonnet-5")
PRICE_IN = 2.0                                                                           
PRICE_OUT = 10.0                            
SPEND_CAP_USD = float(os.environ.get("MD_CLAUDE_CAP", "2.30"))
LEDGER = pathlib.Path(os.environ.get("MD_CLAUDE_LEDGER", "/tmp/v3/claude_spend.jsonl"))
TIMEOUT = (30, 300)

class SpendCapHit(Exception):
    pass

def enabled():
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("MD_NO_CLAUDE") != "1"

def spent_usd():
    total = 0.0
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            try:
                total += json.loads(line).get("cost_usd", 0.0)
            except json.JSONDecodeError:
                continue
    return total

def _record(model, usage, note):
    it, ot = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0)
    cost = it * PRICE_IN / 1e6 + ot * PRICE_OUT / 1e6 + cr * PRICE_IN * 0.1 / 1e6 + cw * PRICE_IN * 1.25 / 1e6
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps({"ts": time.strftime("%H:%M:%S"), "model": model,
                            "in": it, "out": ot, "cost_usd": round(cost, 5), "note": note,
                            "provider": "claude"}) + "\n")
    return cost

def claude_text(prompt, max_tokens, temperature, note=""):
    """One Anthropic messages call; returns (text, usage). Raises SpendCapHit over cap."""
    if spent_usd() >= SPEND_CAP_USD:
        raise SpendCapHit(f"claude spend cap ${SPEND_CAP_USD} reached")
    key = os.environ["ANTHROPIC_API_KEY"]
    print(f"[claude] call start max_tokens={max_tokens} note={note}", flush=True)
    import signal as _sig

    class _ClaudeDeadline(Exception):
        pass

    def _alarm(_signum, _frame):
        raise _ClaudeDeadline("claude hard deadline")

    import threading as _th
    _main = _th.current_thread() is _th.main_thread()
    if _main:
        _sig.signal(_sig.SIGALRM, _alarm)
        _sig.alarm(300)
    try:
        r = requests.post(ANTHROPIC_URL,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": CLAUDE_MODEL, "max_tokens": max_tokens, "stream": True,
                                "messages": [{"role": "user", "content": prompt}]},
                          timeout=TIMEOUT, stream=True)
    finally:
        if _main:
            _sig.alarm(0)
    if r.status_code >= 400:
        low = r.text.lower()
        if "credit" in low or "billing" in low or "balance" in low or "payment" in low:
            raise SpendCapHit(f"claude billing/credit error {r.status_code}: {r.text[:200]}")
    if r.status_code != 200:
        log(f"claude HTTP {r.status_code}: {r.text[:200]}")
    r.raise_for_status()
    parts, usage = [], {}
    last_data = time.time()
    try:
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            if time.time() - last_data > 90:
                r.close()
                raise requests.Timeout("claude stream silent 90s")
            last_data = time.time()
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            if ev.get("type") == "content_block_delta":
                parts.append(ev.get("delta", {}).get("text", ""))
            elif ev.get("type") == "message_delta":
                usage = ev.get("usage", usage)
            elif ev.get("type") == "message_start":
                usage = {**ev.get("message", {}).get("usage", {}), **usage}
    except Exception:
                                                                                      
        if usage:
            _record(CLAUDE_MODEL, usage, note + ":incomplete-stream")
        raise
    text = "".join(parts)
    _record(CLAUDE_MODEL, usage, note)
    return text, usage

def call_json_with_fallback(call_json_fn, kind, prompt, max_tokens, temperature, reasoning,
                            expect=None, parse=None):
    """Try NVIDIA via call_json_fn; on any failure, fall back to Claude if enabled."""
    try:
        out = call_json_fn(kind, prompt, max_tokens, temperature, reasoning, expect=expect)
        with open(LEDGER, "a") as lf:
            lf.write(json.dumps({"ts": time.strftime("%H:%M:%S"), "model": "nvidia",
                                 "in": 0, "out": 0, "cost_usd": 0.0,
                                 "note": f"nvidia:{kind}", "provider": "nvidia"}) + "\n")
        return out
    except Exception as nvidia_err:
        with open(LEDGER, "a") as lf:
            lf.write(json.dumps({"ts": time.strftime("%H:%M:%S"), "model": "nvidia",
                                 "in": 0, "out": 0, "cost_usd": 0.0,
                                 "note": f"nvidia-fail:{kind}", "provider": "nvidia",
                                 "error": str(nvidia_err)[:160]}) + "\n")
        if not enabled():
            raise
        for attempt in range(2):
            p = prompt + (" IMPORTANT: reply with valid compact JSON and nothing else." if attempt else "")
            try:
                text, usage = claude_text(p, max_tokens, temperature, note=f"fallback:{kind}")
            except Exception as ce:
                last = ce
                with open("/tmp/v3/claude_rejects.log", "a") as rf:
                    rf.write(f"--- {time.strftime('%H:%M:%S')} {kind} attempt {attempt} CALL FAILED: {ce}\n\n")
                continue
            try:
                return parse(text, expect=expect)
            except ValueError as e:
                last = e
                with open("/tmp/v3/claude_rejects.log", "a") as rf:
                    rf.write(f"--- {time.strftime('%H:%M:%S')} {kind} attempt {attempt}: {e}\n{text[:1500]}\n\n")
        raise ValueError(f"claude fallback unparseable after NVIDIA failure {nvidia_err}: {last}")

