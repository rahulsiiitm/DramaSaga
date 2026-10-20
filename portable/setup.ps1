param([switch]$Cuda)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ required' }
$Py = Join-Path $PWD '.venv/Scripts/python.exe'
& $Py -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed' }
if ($Cuda) {
  throw 'Install PyTorch for your exact GPU/CUDA from https://pytorch.org/get-started/locally/ then run .venv/Scripts/python -m pip install -r requirements/local.txt. No guessed CUDA wheel.'
}
& $Py -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'PyTorch install failed' }
& $Py -m pip install -r requirements/local.txt --index-url https://pypi.org/simple
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed' }
& $Py portable/doctor.py
if ($LASTEXITCODE -ne 0) { throw 'Install FFmpeg/ffprobe separately from https://ffmpeg.org/download.html and rerun doctor' }
