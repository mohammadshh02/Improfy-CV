# Improfy CV-System

Web-App, die aus einem Lebenslauf (Text, PDF, Screenshot oder Foto) automatisch die
Improfy-Excel-Vorlage befüllt — plus Design-Galerie für PDF-Exporte.

## Schnellstart

```bash
cd cv_system
pip3 install --user flask openpyxl anthropic
cp .env.example .env      # optional, siehe unten
PORT=8000 python3 server.py
```

Dann http://localhost:8000 öffnen. Alternativ per Doppelklick auf
`CV-App starten.command` (startet den Server und öffnet den Browser).

## KI-Anbindung

Die App braucht einen von zwei Wegen, um CVs auszulesen und Designs zu bauen:

1. **Lokale Claude-Code-CLI** (Standard) — nutzt das vorhandene `claude`-Binary via
   `claude -p ... --allowedTools Read`. Kein API-Key nötig. Ca. 20–40 s pro CV.
2. **Anthropic API** — `ANTHROPIC_API_KEY` in `cv_system/.env` setzen. Schneller.

Ist keiner von beiden verfügbar, laufen nur die manuellen Formularwege.

## Aufbau

| Datei | Zweck |
|---|---|
| `cv_system/server.py` | Flask-App, alle Routen |
| `cv_system/fill_cv.py` | Kern-Füll-Logik für die Excel-Vorlage (`fuelle_blatt`) |
| `cv_system/extract_cv.py` | CV → JSON via Anthropic API |
| `cv_system/schema.py` | Datenvertrag für den CV-JSON |
| `cv_system/templates/` | Jinja-Templates: Formular + CV-Designs |
| `cv_system/vorlagen/` | Excel-Vorlage (`Muster-Vorlage.xlsx`) |
| `cv_system/static/vorlagen/` | Referenzbilder der Design-Galerie |

Die befüllten Excel-Dateien landen in `cv_system/ausgabe/`.

## Voraussetzungen

- Python 3.9+
- Google Chrome (für den PDF-Export via Headless-Rendering)
- LibreOffice (nur zum Neu-Rendern der Galerie-Referenzbilder)

## Hinweis zu Daten

Kundendaten (`ausgabe/`, die personenbezogenen `*.json`, Kunden-`*.xlsx`) und
Secrets (`.env`) sind bewusst per `.gitignore` ausgeschlossen und bleiben lokal.
