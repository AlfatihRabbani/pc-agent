@echo off
REM ── PC-Agent one-time setup (Windows) ───────────────────────────────
setlocal
cd /d "%~dp0\.."

echo [1/4] Creating virtual environment (.venv)...
py -3.11 -m venv .venv 2>nul || python -m venv .venv
call .venv\Scripts\activate.bat

echo [2/4] Upgrading pip...
python -m pip install --upgrade pip

echo [3/4] Installing PyTorch + torchvision (CUDA 12.1 build for the 3080 Ti)...
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

echo [4/4] Installing PC-Agent requirements...
pip install -r requirements.txt

echo.
echo Done. Next:
echo   1) huggingface-cli login           (to pull Gemma 4)
echo   2) python scripts\download_models.py
echo   3) python run.py --dry             (test the PC-control tools, no model)
echo   4) python run.py                   (full agent)
endlocal
