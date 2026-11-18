@echo off
rem Startet Purelapse unter Windows.
rem Beim ersten Start wird eine eigene Python-Umgebung angelegt und
rem alles Noetige aus dem Internet geladen (einige Minuten).
cd /d "%~dp0"
if not exist ".venv-win\Scripts\python.exe" (
    echo Richte Python-Umgebung ein ...
    py -3 -m venv .venv-win 2>nul || python -m venv .venv-win
    if not exist ".venv-win\Scripts\python.exe" (
        echo Python wurde nicht gefunden. Bitte Python 3 von python.org installieren
        echo und dabei "Add python.exe to PATH" ankreuzen.
        pause
        exit /b 1
    )
    ".venv-win\Scripts\python.exe" -m pip install --upgrade pip
    ".venv-win\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Die Installation der Pakete ist fehlgeschlagen.
        pause
        exit /b 1
    )
)
start "" ".venv-win\Scripts\pythonw.exe" purelapse_main.py
