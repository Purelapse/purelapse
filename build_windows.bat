@echo off
rem Baut Purelapse unter Windows als eine einzelne Datei: dist\Purelapse.exe
rem Die .exe enthaelt Python, Qt, OpenCV, rawpy und FFmpeg. Auf dem
rem Zielrechner wird nur RawTherapee und/oder ART gebraucht.
rem Voraussetzung zum Bauen: Python 3 von python.org und Internet.
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
)
".venv-win\Scripts\python.exe" -m pip install --upgrade pip
".venv-win\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo Die Installation der Pakete ist fehlgeschlagen.
    pause
    exit /b 1
)
".venv-win\Scripts\python.exe" -m PyInstaller --noconfirm --clean purelapse.spec
if errorlevel 1 (
    echo Der Bau ist fehlgeschlagen - Meldungen oben pruefen.
    pause
    exit /b 1
)
echo.
echo Fertig: %cd%\dist\Purelapse.exe
pause
