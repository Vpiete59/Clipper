@echo off
rem Lance Clipper (fenetre de bureau). Premiere fois : installe l'environnement.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Installation de l'environnement Python, patiente quelques minutes...
  uv sync || (echo uv est introuvable : winget install astral-sh.uv & pause & exit /b 1)
)
if not exist "ui\dist\index.html" (
  pushd ui && call npm install && call npm run build && popd
)
start "" ".venv\Scripts\pythonw.exe" -m clipper.app
