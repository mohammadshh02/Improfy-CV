#!/usr/bin/env python3
"""
cv.py  —  ALLES IN EINEM SCHRITT.

Wirf beliebige/unsortierte Daten (PDF oder Text) rein → fertige Excel raus.
Die KI sortiert automatisch, fill_cv.py setzt sie ins Muster (1:1-Optik) und
markiert, was noch fehlt.

Aufruf:
  python3 cv.py  "Lebenslauf.pdf"  "ID-K0148_Max_Mustermann"
  python3 cv.py  "rohdaten.txt"    "ID-K0148_Max_Mustermann"

Optional:  --master <pfad>   --out <ordner>
Voraussetzung:  export ANTHROPIC_API_KEY="sk-ant-..."
"""
import argparse
import os
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="CV-PDF oder Textdatei mit (unsortierten) Rohdaten")
    ap.add_argument("blatt_name", help='z.B. "ID-K0148_Max_Mustermann"')
    ap.add_argument("--master", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        json_pfad = tmp.name

    py = sys.executable
    # 1) KI: unsortierte Daten -> strukturiertes JSON
    print("① Daten werden von der KI sortiert …")
    subprocess.run([py, os.path.join(HIER, "extract_cv.py"), args.input, json_pfad],
                   check=True, cwd=HIER)
    # 2) JSON -> Excel (Tab + Einzel-Datei + Checkliste)
    print("② Excel wird befüllt …")
    cmd = [py, os.path.join(HIER, "fill_cv.py"), json_pfad, args.blatt_name]
    if args.master:
        cmd += ["--master", args.master]
    if args.out:
        cmd += ["--out", args.out]
    subprocess.run(cmd, check=True, cwd=HIER)

    os.unlink(json_pfad)
    print("\n✓ Fertig.")


if __name__ == "__main__":
    main()
