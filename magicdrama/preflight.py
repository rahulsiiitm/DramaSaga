import json
import shutil
import sys

from . import config
from .canon import CANON
from .ledgers import ensure_ledgers
from .validation import validate_brief, validate_canon, validate_config

def run_checks(brief, workdir=None):
    checks = []
    checks.append(("python>=3.9", sys.version_info >= (3, 9), sys.version.split()[0]))
    try:
        import requests
        checks.append(("requests importable", True, requests.__version__))
    except Exception as e:
        checks.append(("requests importable", False, str(e)))
    errs = validate_brief(brief)
    checks.append(("brief valid", not errs, "; ".join(errs) or "ok"))
    errs = validate_canon(CANON)
    checks.append(("canon valid", not errs, "; ".join(errs) or f"{len(CANON)} episodes"))
    errs = validate_config()
    checks.append(("config valid", not errs, "; ".join(errs) or "ok"))
    try:
        w = workdir or config.WORKDIR
        w.mkdir(exist_ok=True)
        ensure_ledgers(w)
        probe = w / ".preflight_probe"
        probe.write_text("ok")
        probe.unlink()
        checks.append(("workdir writable", True, str(w)))
    except Exception as e:
        checks.append(("workdir writable", False, str(e)))
    ffmpeg = shutil.which("ffmpeg")
    checks.append(("ffmpeg for assembly", bool(ffmpeg), ffmpeg or "not found; needed at assembly stage"))
    if not config.DRY_RUN:
        from .clients.nvidia import get_key
        checks.append(("NVIDIA_KEY present", bool(get_key("NVIDIA_KEY")), "env or colab secret"))
        checks.append(("MAGICHOUR_KEY present", bool(get_key("MAGICHOUR_KEY")), "env or colab secret"))
    return checks

def report(brief, workdir=None):
    checks = run_checks(brief, workdir)
    ok = True
    for name, passed, detail in checks:
        print(("PASS" if passed else "FAIL"), "-", name, "-", detail)
        ok = ok and passed
    return ok

