#!/usr/bin/env sh
# Startskript des Addons: wechselt ins App-Verzeichnis und startet den Webserver
cd /app || exit 1
exec python3 main.py
