"""Einstiegspunkt für Vercel.

Vercel sucht in /api nach Python-Dateien und erwartet eine WSGI-Variable `app`.
Die eigentliche App liegt eine Ebene höher in server.py – wir hängen den
Elternordner in den Importpfad und reichen die Flask-App durch.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app  # noqa: E402  (Import muss nach dem sys.path-Eintrag stehen)

__all__ = ["app"]
