# Bau-Umgebung fuer Purelapse.
# Ubuntu 22.04 = Basis von Linux Mint 21. Was hier gebaut wird, laeuft auf
# Mint 21.x und allen neueren Versionen (Mint 22.x ...).
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# Python 3.12 (wie auf dem Entwicklungsrechner) + Werkzeuge
RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common gpg-agent ca-certificates binutils \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends python3.12 python3.12-venv libpython3.12 \
 && rm -rf /var/lib/apt/lists/*

# Systembibliotheken, die Qt fuer die Fensterdarstellung (X11) braucht.
# PyInstaller packt sie mit in die Einzeldatei.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1 libegl1 libglib2.0-0 libfontconfig1 libfreetype6 libdbus-1-3 \
      libx11-xcb1 libxcb1 libxcb-glx0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
      libxcb-randr0 libxcb-render0 libxcb-render-util0 libxcb-shape0 libxcb-shm0 \
      libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 libxcb-util1 \
      libxkbcommon0 libxkbcommon-x11-0 libxrender1 libxext6 libsm6 libice6 \
 && rm -rf /var/lib/apt/lists/*

# appimagetool zum Zusammenpacken des AppImages. Laeuft im Container ohne
# FUSE ueber APPIMAGE_EXTRACT_AND_RUN (siehe appimage/innen.sh).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl file \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fL -o /opt/appimagetool \
      https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
 && chmod 755 /opt/appimagetool

COPY requirements.txt /tmp/requirements.txt
RUN python3.12 -m venv /opt/venv \
 && /opt/venv/bin/python -m pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt pyinstaller

ENV HOME=/tmp PYINSTALLER_CONFIG_DIR=/tmp/pyinstaller
WORKDIR /src
