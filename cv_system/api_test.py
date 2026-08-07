#!/usr/bin/env python3
"""Prüft, ob der ANTHROPIC_API_KEY in .env funktioniert.

Aufruf:  python3 api_test.py
"""
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))

# .env laden – gleiche Logik wie server.py
envfile = os.path.join(HIER, ".env")
if os.path.exists(envfile):
    for line in open(envfile, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
if not key:
    sys.exit("FEHLT: ANTHROPIC_API_KEY ist leer. Key in cv_system/.env eintragen.")
print(f"Key gefunden: {key[:14]}... ({len(key)} Zeichen)")

import anthropic

client = anthropic.Anthropic()
try:
    resp = client.messages.create(
        model="claude-opus-5",
        max_tokens=64,
        messages=[{"role": "user", "content": "Antworte nur mit: OK"}],
    )
except anthropic.AuthenticationError:
    sys.exit("FEHLER: Key wird abgelehnt (ungueltig oder geloescht).")
except anthropic.PermissionDeniedError:
    sys.exit("FEHLER: Key hat keine Berechtigung fuer dieses Modell.")
except anthropic.RateLimitError:
    sys.exit("FEHLER: Rate-Limit erreicht – spaeter erneut versuchen.")
except anthropic.APIStatusError as e:
    sys.exit(f"FEHLER {e.status_code}: {e.message}")

antwort = next((b.text for b in resp.content if b.type == "text"), "")
print(f"Antwort:      {antwort.strip()}")
print(f"Modell:       {resp.model}")
print(f"Tokens:       {resp.usage.input_tokens} rein / {resp.usage.output_tokens} raus")
print("\nOK – die App nutzt ab jetzt die API statt der Claude-CLI.")
