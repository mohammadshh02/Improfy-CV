#!/usr/bin/env python3
"""
extract_cv.py  —  Liest CV-Daten (PDF ODER beliebiger Text) und sortiert sie
automatisch in strukturiertes JSON (schema.py).

Die Daten dürfen völlig UNSORTIERT / durcheinander sein — die KI ordnet sie
selbstständig den richtigen Feldern zu.

Voraussetzung:  pip install anthropic   und   export ANTHROPIC_API_KEY="sk-ant-..."

Aufruf:
  python3 extract_cv.py  "Lebenslauf.pdf"   kandidat.json     # PDF
  python3 extract_cv.py  "rohdaten.txt"     kandidat.json     # Textdatei
"""
import argparse
import base64
import json
import os
import sys

import anthropic

from schema import CV_JSON_SCHEMA

SYSTEM = """Du bist Assistenz bei Improfy GmbH (Bewerbungscoaching). Du bekommst
die Angaben eines Kunden – oft UNSORTIERT, unvollständig oder als lose Notizen –
und ordnest sie selbstständig den richtigen Feldern der CV-Vorlage zu.

Regeln:
- Sortiere alles automatisch ein: Name, Kontakt, Jobs, Ausbildung, Sprachen usw.
- 'geschlecht' (m/w/d) aus Vorname/Anrede/Foto ableiten.
- Übernimm NUR echte Angaben. Erfinde keine Firmen, Daten oder Noten.
- Zeiträume im Format mm.yyyy - mm.yyyy (Punkt, nicht Slash). 'seit mm.yyyy' für laufende.
- Berufserfahrung + Bildung: neueste zuerst.
- 'angestrebter_job': aussagekräftige Ziel-Bezeichnung aus dem Werdegang ableiten.
- Tätigkeiten: 2-4 knappe, branchenübliche Stichpunkte pro Station (aus Jobtitel ableitbar).
- Sprachen: Deutsch IMMER zuerst, Sprachnamen in GROSSBUCHSTABEN.
- soft_skills: max. 8 zum Werdegang passende Eigenschaften (Sterne 3-5).
- 'ueber_mich': fertiger, freundlicher Text in Ich-Form (4-6 Absätze), beginnend mit
  'Guten Tag,' und endend mit 'Mit freundlichen Grüßen' + vollem Namen.
- Fehlt eine Angabe, lass das Feld leer ('' bzw. []). NICHT raten.
- Handschriftliche Notizen/Ergänzungen mit einbeziehen."""

PDF_ENDUNGEN = (".pdf",)
TEXT_ENDUNGEN = (".txt", ".md", ".text", "")


def baue_inhalt(pfad):
    """Erzeugt den content-Block je nach Dateityp (PDF vs. Text)."""
    endung = os.path.splitext(pfad)[1].lower()
    if endung in PDF_ENDUNGEN:
        with open(pfad, "rb") as fh:
            b64 = base64.standard_b64encode(fh.read()).decode("utf-8")
        return [
            {"type": "document",
             "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
            {"type": "text", "text": "Sortiere diese CV-Daten in die Vorlage."},
        ]
    # sonst: als Text behandeln
    with open(pfad, encoding="utf-8") as fh:
        roh = fh.read()
    return [{"type": "text",
             "text": "Hier sind die (evtl. unsortierten) Kundendaten:\n\n" + roh
                     + "\n\nSortiere sie in die Vorlage."}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="CV-PDF oder Textdatei mit Rohdaten")
    ap.add_argument("json_out", help="Ziel-JSON-Datei")
    ap.add_argument("--model", default="claude-opus-4-8")
    args = ap.parse_args()

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=args.model,
        max_tokens=8000,
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": CV_JSON_SCHEMA}},
        messages=[{"role": "user", "content": baue_inhalt(args.input)}],
    )

    if resp.stop_reason == "refusal":
        sys.exit("Anfrage wurde abgelehnt (stop_reason=refusal).")
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)

    with open(args.json_out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"✓ Daten sortiert → {args.json_out}")
    print(f"  {data.get('vorname')} {data.get('nachname')} | "
          f"{len(data.get('berufserfahrung', []))} Stationen, "
          f"{len(data.get('bildung', []))} Bildungseinträge")


if __name__ == "__main__":
    main()
