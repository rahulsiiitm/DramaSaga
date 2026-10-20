#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip --index-url https://pypi.org/simple
.venv/bin/python -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements/local.txt --index-url https://pypi.org/simple
.venv/bin/python portable/doctor.py
