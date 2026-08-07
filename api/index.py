"""Einstiegspunkt für Vercel.

Vercel sucht im Ordner /api der Repo-Wurzel nach Python-Dateien und erwartet
eine WSGI-Variable `app`. Die eigentliche App liegt in cv_system/server.py –
wir hängen diesen Ordner in den Importpfad und reichen die Flask-App durch.

Liegt bewusst in der Wurzel, damit in den Vercel-Projekteinstellungen kein
abweichendes Root Directory gesetzt werden muss.
"""
import os
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WURZEL, "cv_system"))

from server import app  # noqa: E402  (Import muss nach dem sys.path-Eintrag stehen)

__all__ = ["app"]
