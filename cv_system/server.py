#!/usr/bin/env python3
"""
Improfy CV Web-App
==================
Mitarbeiter tippen die Lebenslauf-Infos in ein Formular im Browser →
die CV-Vorlage (Muster) wird automatisch ausgefüllt →
fertige, kopier- und bearbeitbare Excel zum Download.

Start:
  cd ~/Desktop/Improfy/cv_system
  python3 server.py
Dann im Browser öffnen:  http://localhost:5000
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import tempfile

import openpyxl
from flask import Flask, jsonify, render_template, request, send_file

import fill_cv  # nutzt die bestehende Füll-/Style-/Entmerge-Logik
from schema import CV_JSON_SCHEMA

HIER = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_XLSX = os.path.join(HIER, "vorlagen", "Muster-Vorlage.xlsx")

# .env laden (falls vorhanden) -> stellt z.B. ANTHROPIC_API_KEY bereit
_envfile = os.path.join(HIER, ".env")
if os.path.exists(_envfile):
    for _line in open(_envfile, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

app = Flask(__name__)


@app.after_request
def _kein_cache(resp):
    # verhindert, dass der Browser eine alte Version der App anzeigt
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ----------------------------------------------------- Formular -> Daten-Dict
def _liste(form, *keys):
    """Parallele Formularlisten zu Zeilen zusammenführen (robust bei ungleicher Länge)."""
    from itertools import zip_longest
    spalten = [form.getlist(k + "[]") for k in keys]
    zeilen = []
    for werte in zip_longest(*spalten, fillvalue=""):
        zeilen.append(dict(zip(keys, [(w or "").strip() for w in werte])))
    return zeilen


def _zeilen(text):
    return [z.strip() for z in (text or "").splitlines() if z.strip()]


def _sterne(v, default=4):
    try:
        return max(1, min(5, int(v)))
    except (TypeError, ValueError):
        return default


def build_data(form):
    g = lambda k: (form.get(k) or "").strip()
    data = {
        "kunde_von": g("kunde_von") or fill_cv.DEFAULT_KUNDE_VON,
        "vorname": g("vorname"),
        "nachname": g("nachname"),
        "geschlecht": g("geschlecht"),
        "angestrebter_job": g("angestrebter_job"),
        "geburtsdatum": g("geburtsdatum"),
        "mobil": g("mobil"),
        "email": g("email"),
        "adresse": g("adresse"),
        "fuehrerschein": {
            "vorhanden": form.get("fs_vorhanden") == "on",
            "klasse": g("fs_klasse"),
            "eu": form.get("fs_eu") == "on",
        },
        "ueber_mich": g("ueber_mich"),
        "hobbys": g("hobbys"),
        "zusatzqualifikationen": _zeilen(g("zusatzqual")),
        "berufserfahrung": [],
        "bildung": [],
        "sprachen": [],
        "edv_kenntnisse": [],
        "soft_skills": [],
    }
    # Berufserfahrung
    for r in _liste(form, "beruf_zeitraum", "beruf_firma", "beruf_jobtitel", "beruf_taet"):
        if any([r["beruf_zeitraum"], r["beruf_firma"], r["beruf_jobtitel"]]):
            data["berufserfahrung"].append({
                "zeitraum": r["beruf_zeitraum"], "firma": r["beruf_firma"],
                "jobtitel": r["beruf_jobtitel"],
                "taetigkeiten": _zeilen(r["beruf_taet"]),
            })
    # Bildung
    for r in _liste(form, "bild_zeitraum", "bild_abschluss", "bild_institution", "bild_note"):
        if any([r["bild_zeitraum"], r["bild_abschluss"], r["bild_institution"]]):
            data["bildung"].append({
                "zeitraum": r["bild_zeitraum"], "abschluss": r["bild_abschluss"],
                "institution": r["bild_institution"], "note": r["bild_note"],
            })
    # Sprachen
    for r in _liste(form, "spr_sprache", "spr_niveau"):
        if r["spr_sprache"]:
            data["sprachen"].append({"sprache": r["spr_sprache"], "niveau": r["spr_niveau"]})
    # EDV
    for r in _liste(form, "edv_programm", "edv_sterne"):
        if r["edv_programm"]:
            data["edv_kenntnisse"].append({"programm": r["edv_programm"], "sterne": _sterne(r["edv_sterne"])})
    # Soft Skills
    for r in _liste(form, "ss_eigenschaft", "ss_sterne"):
        if r["ss_eigenschaft"]:
            data["soft_skills"].append({"eigenschaft": r["ss_eigenschaft"], "sterne": _sterne(r["ss_sterne"], 5)})
    return data


def _safe_sheetname(name):
    name = re.sub(r'[\[\]:*?/\\]', "", name) or "Kandidat"
    return name[:31]


def generate_xlsx(data):
    wb = openpyxl.load_workbook(TEMPLATE_XLSX)
    ws = wb["Muster"]
    ws.title = _safe_sheetname(f"{data['vorname']} {data['nachname']}".strip())
    fehlend = fill_cv.fuelle_blatt(ws, data)  # füllen + schwarz/Gr.12 + entmerge
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio, fehlend


def xlsx_antwort(data):
    """Erzeugt die Excel und liefert JSON: Datei (base64) + Feedback (was fehlt)."""
    bio, fehlend = generate_xlsx(data)
    name = f"{data.get('vorname', '')}_{data.get('nachname', '')}".strip("_") or "Lebenslauf"
    name = re.sub(r"\s+", "_", name) + ".xlsx"
    fehlend_txt = [f"{feld}" + (f" (Zelle {zelle})" if zelle else "") for feld, zelle in fehlend]
    return jsonify({
        "filename": name,
        "fehlend": fehlend_txt,
        "daten": data,          # für die In-App-Vorschau
        "file_b64": base64.b64encode(bio.getvalue()).decode("ascii"),
    })


# ---------------------------------------- Designter CV (HTML -> PDF über Chrome)
CHROME = next((p for p in [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
] if os.path.exists(p)), None)

# Schnelle, feste HTML-Designs (zuverlässig, mehrseitig, ~3 s). Weitere Stile generiert Claude.
DESIGNS = {"pro": "cv_pro.html", "gruen": "cv_gruen.html", "clean": "cv_clean.html", "blob": "cv_blob.html"}


def _niveau_txt(sterne):
    return {5: "Sehr gute Kenntnisse", 4: "Gute Kenntnisse",
            3: "Grundkenntnisse", 2: "Grundkenntnisse", 1: "Grundkenntnisse"}.get(int(sterne or 0), "Gute Kenntnisse")


def html_to_pdf(html):
    tmpd = tempfile.mkdtemp()
    hp = os.path.join(tmpd, "cv.html")
    pp = os.path.join(tmpd, "cv.pdf")
    with open(hp, "w", encoding="utf-8") as fh:
        fh.write(html)
    try:
        subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                        "--no-pdf-header-footer", "--print-to-pdf-no-header",
                        f"--print-to-pdf={pp}", "file://" + hp],
                       capture_output=True, timeout=90)
        with open(pp, "rb") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def improfy_block(daten):
    g = (daten.get("geschlecht") or "").strip().lower()
    tn = "Teilnehmerin" if g == "w" else "Teilnehmer"
    return {"zeitraum": "aktuell", "jobtitel": tn, "firma": "Improfy GmbH, Köln",
            "taetigkeiten": ["Bewerbungsvorbereitung", "Training Vorstellungsgespräche",
                             "Aktive Kontaktaufnahme mit Unternehmen"]}


# ---- Design-Engine 2: Lebenslauf-HTML von Claude Code generieren lassen ----
PLACEHOLDER_FOTO = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' "
                    "width='150' height='184'><rect width='100%25' height='100%25' fill='%23eef1f4'/></svg>")


def _logo_uri():
    try:
        with open(os.path.join(app.root_path, "static", "improfy-logo.png"), "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""


LOGO_URI = _logo_uri()

STILE = {
    "modern_blau": "Modern mit Blau/Petrol (#0e7490) als Leitfarbe: farbiges Kopf-Banner mit Namen, blaue "
                   "Überschriften, Datums-Spalte und Zeitstrahl-Optik in Blau. Einspaltig-fließend, klar und modern.",
    "klassisch": "Klassisch-seriös: reduziert, viel Weißraum, feine Trennlinien, Schwarz/Anthrazit mit einem dezenten "
                 "dunkelblauen Akzent (#1d3b8b), klassische, gut lesbare Typografie. Sehr aufgeräumt.",
    "elegant": "Elegant: dunkler Kopfbereich (Anthrazit #1f2937) mit hellem Namen, Akzentfarbe Türkis (#0d9488), "
               "viel Weißraum, feine Linien, hochwertige Anmutung.",
    "gruen": "Improfy-Grün #8DC63F als Leitfarbe; grünes Kopf-Banner, grüne Überschriften, Foto mit grünem Rahmen.",
}

CV_DESIGN_SYSTEM = """Du bist Grafik-/Webdesigner. Erzeuge einen fertigen, druckreifen Lebenslauf
als EIN einzelnes, in sich geschlossenes HTML-Dokument (HTML + eingebettetes <style>), Format DIN A4.

Stil / Leitfarbe: __STIL__

Aufbau (verbindlich):
- Kopf mit dem NAMEN groß (Vorname über Nachname) – je nach Stil als farbiges Banner oder in der Seitenleiste.
- Foto: exakt <img class="photo" src="__FOTO__"> mit abgerundeten Ecken (~16px) und farbigem Rahmen,
  Porträtformat ca. 150x184. Den Platzhalter __FOTO__ NICHT verändern.
- Kontaktzeilen: Geboren, Adresse, Telefon, E-Mail, Ziel.
- Sektionen in dieser Reihenfolge, farbige Überschriften (Leitfarbe): ÜBER MICH, BERUFSERFAHRUNG,
  PERSÖNLICHE QUALIFIKATION (Unterpunkte: EDV-Kenntnisse, Stärken), SCHUL- & AUSBILDUNG, SPRACHKENNTNISSE.
- BERUFSERFAHRUNG: als ERSTEN Eintrag "(aktuell) TEILNEHMER_TITEL | Improfy GmbH, Köln" mit Punkten:
  Bewerbungsvorbereitung; Training Vorstellungsgespräche; Aktive Kontaktaufnahme mit Unternehmen.
- EDV-Kenntnisse: sterne 5 -> "Sehr gute Kenntnisse", 4 -> "Gute Kenntnisse", <=3 -> "Grundkenntnisse".
- Stärken (soft_skills): als Sterne ★ (gefüllt) und ☆ (leer) gemäß sterne (1-5).
- WICHTIG (mehrseitig, verbindlich): KEINE durchgehende, seitenhohe Seitenleiste / kein vollflächiger Farbbalken
  über die ganze Seitenhöhe – das bricht im PDF und hinterlässt leere Farbflächen auf Folgeseiten. Nutze stattdessen
  ein farbiges Kopf-Banner oben + einspaltigen, fließenden Inhalt; Farbe NUR als Akzent (Linien, Überschriften,
  Datums-Spalte, Zeitstrahl, kleine Boxen). Keine position:fixed-Elemente.
- Druck-sicher: @page { size:A4; margin:12mm 13mm 14mm; } und break-inside:avoid für jeden Eintrag,
  damit der mehrseitige Umbruch sauber ist (keine Überlappungen/abgeschnittenen Einträge).
- Leere Felder/Sektionen weglassen. Moderne, saubere, gut lesbare Typografie.

Gib AUSSCHLIESSLICH das HTML-Dokument zurück – KEIN Markdown, KEINE Code-Fences, KEIN Kommentar."""


def design_via_claude(daten, stil="gruen"):
    g = (daten.get("geschlecht") or "").strip().lower()
    tn = "Teilnehmerin" if g == "w" else "Teilnehmer"
    prompt = (CV_DESIGN_SYSTEM.replace("__STIL__", STILE.get(stil, STILE["gruen"])).replace("TEILNEHMER_TITEL", tn)
              + "\n\nBewerber-Daten (JSON):\n" + json.dumps(daten, ensure_ascii=False, indent=1))
    r = subprocess.run([CLAUDE_BIN, "-p", prompt, "--output-format", "text"],
                       capture_output=True, text=True, timeout=300)
    out = (r.stdout or "").strip()
    lo = out.lower()
    i = lo.find("<!doctype")
    if i < 0:
        i = lo.find("<html")
    j = lo.rfind("</html>")
    if i >= 0 and j >= 0:
        return out[i:j + 7]
    raise RuntimeError("Claude hat kein gültiges HTML geliefert.")


# --------------------------------------------- Vorlagen-Galerie (find-hire Reproduktion)
VORLAGEN_DIR = os.path.join(app.root_path, "static", "vorlagen")


def lade_vorlagen():
    try:
        with open(os.path.join(VORLAGEN_DIR, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


VORLAGEN = lade_vorlagen()
VORLAGEN_BY_ID = {v["id"]: v for v in VORLAGEN}

REPRO_PROMPT = """Lies zuerst das Referenzbild mit dem Read-Tool: __REF__

Im Bild siehst du ein fertiges CV-Design. Baue GENAU DIESES Design als EIN druckreifes A4-HTML-Dokument nach (HTML + eingebettetes <style>).

SEHR WICHTIG – Bild richtig lesen:
- Der HINTERGRUND des Designs ist WEISS (falls nicht klar erkennbar: weiß annehmen). Übernimm die echten Design-Farben (z.B. Gelb, Blau, Navy, Pink, Türkis) als Akzente.
- SCHWARZE Rechtecke im Bild sind NUR Foto-Platzhalter (Render-Artefakt), KEINE Design-Farbe. Dorthin kommt das Foto. Färbe NICHTS großflächig schwarz/dunkel ein.
- Farbige Formen (Blobs, Balken, Punkte) exakt in Position/Größe/Farbe wie im Original übernehmen – aber nur als Akzent, nicht die ganze Seite zufärben.
- TEXT immer in kräftiger, dunkler Farbe auf hellem Grund (oder hell auf dunklem Akzent), hoher Kontrast, absolut gut lesbar.

GRÖSSE & LESBARKEIT (SEHR WICHTIG – das Ergebnis soll groß & hochwertig wirken, NICHT winzig):
- GROSSE, gut lesbare Schrift: Grundtext ca. 14–15px, Zeilenhöhe ~1.6, großzügige Abstände zwischen Absätzen/Einträgen.
- Abschnitts-Überschriften GROSS (~24–28px), fett, klare Hierarchie. Name im Kopf sehr groß (~30–40px).
- Nutze die A4-Seite gut aus (Ränder ~14–16mm). Lieber großzügig & luftig als gedrängt. 2–3 Seiten sind völlig in Ordnung.
- Foto deutlich sichtbar (~45mm breit), wie im Original platziert.
- Wenn das Original 2 Spalten hat (Foto/Kontakt links, Inhalt rechts), setze das so um. Wiederholender Kopf pro Seite ist erwünscht, wenn das Original ihn hat (z.B. via <thead> in einer Tabelle).
- Der farbige Blob/Balken/Akzent im Kopf nimmt höchstens das obere Drittel der ersten Seite ein – nicht die ganze Seite zufärben.
- Oben genügend Luft lassen (~8–10mm), damit der Name NICHT am Seitenrand abgeschnitten wird. Nichts darf über den druckbaren Bereich hinausragen.

Inhalt:
- Übernimm exakt Farben, Formen, Anordnung, Typografie, Ausrichtung und Abschnitts-Reihenfolge des Designs.
- ERSETZE alle Beispieltexte (z.B. Max/Martina Mustermann, Marketing Manager, Musteradresse, Beispiel-Jobs) durch die echten Bewerber-Daten unten.
- Foto: exakt <img class="photo" src="__FOTO__"> an der Foto-Stelle. Platzhalter __FOTO__ NICHT verändern.
- Abschnitte: Über mich; Berufserfahrung (erster Eintrag "(aktuell) TEILNEHMER_TITEL | Improfy GmbH, Köln" mit: Bewerbungsvorbereitung; Training Vorstellungsgespräche; Aktive Kontaktaufnahme mit Unternehmen); Persönliche Qualifikation (EDV + Stärken als Sterne ★/☆); Schul- & Ausbildung; Sprachkenntnisse. Leere Felder weglassen.
- Druck-sicher: @page{size:A4;}; break-inside:avoid je Eintrag; bei mehr Inhalt sauber auf Folgeseiten fließen; KEINE seitenhohen dunklen Flächen, KEINE position:fixed.

Gib AUSSCHLIESSLICH das HTML zurück (<!doctype html> … </html>), KEIN Markdown, KEINE Erklärung.

Bewerber-Daten (JSON):
"""


def design_from_reference(daten, ref_path):
    g = (daten.get("geschlecht") or "").strip().lower()
    tn = "Teilnehmerin" if g == "w" else "Teilnehmer"
    prompt = (REPRO_PROMPT.replace("__REF__", ref_path).replace("TEILNEHMER_TITEL", tn)
              + json.dumps(daten, ensure_ascii=False, indent=1))
    r = subprocess.run([CLAUDE_BIN, "-p", prompt, "--allowedTools", "Read", "--output-format", "text"],
                       capture_output=True, text=True, timeout=300)
    out = (r.stdout or "").strip()
    if out.count("&lt;") > 10 and "<html" not in out.lower():
        import html as _htmlmod
        out = _htmlmod.unescape(out)
    lo = out.lower()
    i = lo.find("<!doctype")
    if i < 0:
        i = lo.find("<html")
    j = lo.rfind("</html>")
    if i >= 0 and j >= 0:
        return out[i:j + 7]
    raise RuntimeError("Claude hat kein gültiges HTML geliefert.")


# --------------------------------------------- KI: Rohdaten -> Formular-Daten
KI_SYSTEM = """Du bist Assistenz bei Improfy GmbH (Bewerbungscoaching). Du bekommst
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
- soft_skills: 5-8 zum Werdegang passende Eigenschaften (Sterne 3-5).
- 'ueber_mich': fertiger, freundlicher Text in Ich-Form (4-6 Absätze), beginnend mit
  'Guten Tag,' und endend mit 'Mit freundlichen Grüßen' + vollem Namen.
- Fehlt eine Angabe, lass das Feld leer ('' bzw. []). NICHT raten."""


def ki_extrahiere(text=None, files=None):
    """files = Liste von (mimetype, bytes) – PDFs, Screenshots, Fotos. text = optionale Zusatzinfos."""
    import anthropic
    client = anthropic.Anthropic()
    content = []
    for mt, data in (files or []):
        b64 = base64.standard_b64encode(data).decode("utf-8")
        if mt == "application/pdf":
            content.append({"type": "document",
                            "source": {"type": "base64", "media_type": "application/pdf", "data": b64}})
        elif mt.startswith("image/"):
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": mt, "data": b64}})
    prompt = ("Lies ALLE beigefügten Dokumente, Screenshots und Fotos sorgfältig aus – "
              "auch Schrift/Text, der als Bild vorliegt. Sortiere sämtliche Informationen "
              "individuell in die CV-Vorlage.")
    if text:
        prompt += "\n\nZusätzliche Angaben (bitte mit einbeziehen):\n" + text
    content.append({"type": "text", "text": prompt})
    resp = client.messages.create(
        model="claude-opus-5", max_tokens=16000, system=KI_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": CV_JSON_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Anfrage wurde von der KI abgelehnt.")
    txt = next(b.text for b in resp.content if b.type == "text")
    return json.loads(txt)


# ---- KI-Weg 2: über lokal installiertes Claude Code (nutzt Max-Abo, kein API-Key) ----
CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")

JSON_TEMPLATE = """{
  "kunde_von": "",
  "vorname": "", "nachname": "", "geschlecht": "m|w|d",
  "angestrebter_job": "", "geburtsdatum": "TT.MM.JJJJ",
  "mobil": "", "email": "", "adresse": "Straße Nr, PLZ Ort",
  "fuehrerschein": {"vorhanden": false, "klasse": "", "eu": true},
  "berufserfahrung": [{"zeitraum": "mm.yyyy - mm.yyyy", "firma": "", "jobtitel": "", "taetigkeiten": []}],
  "bildung": [{"zeitraum": "", "abschluss": "", "institution": "", "note": ""}],
  "zusatzqualifikationen": [],
  "sprachen": [{"sprache": "DEUTSCH", "niveau": ""}],
  "edv_kenntnisse": [{"programm": "", "sterne": 4}],
  "soft_skills": [{"eigenschaft": "", "sterne": 5}],
  "ueber_mich": "", "hobbys": ""
}"""


def claude_verfuegbar():
    return os.path.exists(CLAUDE_BIN)


def ki_via_cli(text=None, file_paths=None):
    teile = [KI_SYSTEM,
             "\nFülle GENAU diese JSON-Struktur aus (identische Schlüssel) und gib "
             "AUSSCHLIESSLICH das JSON zurück – kein Fließtext, keine Markdown-Fences:",
             JSON_TEMPLATE]
    if file_paths:
        teile.append("\nLies diese Datei(en) vollständig aus – auch Schrift auf Bildern/Screenshots/Fotos:")
        teile += [f'- "{p}"' for p in file_paths]
    if text:
        teile.append("\nZusätzliche Angaben (mit einbeziehen):\n" + text)
    prompt = "\n".join(teile)
    r = subprocess.run([CLAUDE_BIN, "-p", prompt, "--allowedTools", "Read", "--output-format", "text"],
                       capture_output=True, text=True, timeout=300)
    out = (r.stdout or "").strip()
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise RuntimeError("Keine JSON-Antwort von Claude Code erhalten. " + (out[:200] or (r.stderr or "")[:200]))
    return json.loads(m.group(0))


def ki_sortieren(text=None, files=None):
    """Dispatcher: API-Key vorhanden -> API (schnell); sonst -> Claude Code (Max-Abo)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ki_extrahiere(text, files)
    if claude_verfuegbar():
        tmpdir = tempfile.mkdtemp()
        try:
            paths = []
            for i, (mt, data) in enumerate(files or []):
                ext = ".pdf" if mt == "application/pdf" else "." + (mt.split("/")[-1] or "png")
                p = os.path.join(tmpdir, f"upload_{i}{ext}")
                with open(p, "wb") as fh:
                    fh.write(data)
                paths.append(p)
            return ki_via_cli(text, paths)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    raise RuntimeError("Keine KI verfügbar (weder API-Schlüssel noch Claude Code gefunden).")


def _sammle_eingaben(req):
    """Text + hochgeladene Dateien (PDF/Bild) aus dem Request holen."""
    text = (req.form.get("rohtext") or "").strip()
    files = []
    for f in req.files.getlist("dateien"):
        if f and f.filename:
            mt = (f.mimetype or "").lower()
            if mt == "application/pdf" or mt.startswith("image/"):
                files.append((mt, f.read()))
    return text, files


# --------------------------------------------------------------------- Routen
@app.route("/")
def index():
    return render_template("form.html", kunde_von=fill_cv.DEFAULT_KUNDE_VON, vorlagen=VORLAGEN)


_KEINE_KI = ("Keine KI verfügbar. Entweder Claude Code installiert lassen (nutzt dein Max-Abo) "
             "oder einen ANTHROPIC_API_KEY in cv_system/.env hinterlegen.")


@app.route("/extract", methods=["POST"])
def extract():
    """KI sortiert Rohdaten (Text/PDF/Bilder) -> JSON zum Vorausfüllen des Formulars."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or claude_verfuegbar()):
        return jsonify({"error": _KEINE_KI}), 400
    text, files = _sammle_eingaben(request)
    if not text and not files:
        return jsonify({"error": "Bitte Text eingeben oder Dateien (PDF/Screenshot/Foto) hochladen."}), 400
    try:
        return jsonify(ki_sortieren(text or None, files))
    except Exception as e:
        return jsonify({"error": f"Fehler bei der KI-Sortierung: {e}"}), 500


@app.route("/generate-auto", methods=["POST"])
def generate_auto():
    """EIN Klick: Rohdaten (Text/PDF/Bilder) -> KI sortiert -> fertige Excel zum Download."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or claude_verfuegbar()):
        return jsonify({"error": _KEINE_KI}), 400
    text, files = _sammle_eingaben(request)
    if not text and not files:
        return jsonify({"error": "Bitte Text eingeben oder Dateien (PDF/Screenshot/Foto) hochladen."}), 400
    try:
        data = ki_sortieren(text or None, files)
    except Exception as e:
        return jsonify({"error": f"Fehler bei der KI-Sortierung: {e}"}), 500
    return xlsx_antwort(data)


# ------------------------------------------------------- Figma-Anbindung (read)
import urllib.parse
import urllib.request

FIGMA_API = "https://api.figma.com/v1"
FIGMA_FILE_DEFAULT = "cCtPg8pX2JuhkWYjQieWzH"  # "Improfy Dateien"


def figma_token():
    return (os.environ.get("FIGMA_TOKEN") or "").strip()


def _figma_get(path):
    req = urllib.request.Request(FIGMA_API + path, headers={"X-Figma-Token": figma_token()})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


@app.route("/figma")
def figma_page():
    return render_template("figma.html", file_key=FIGMA_FILE_DEFAULT, token_ok=bool(figma_token()))


@app.route("/figma/frames")
def figma_frames():
    if not figma_token():
        return jsonify({"error": "Kein Figma-Token hinterlegt (FIGMA_TOKEN in cv_system/.env)."}), 400
    key = request.args.get("file") or FIGMA_FILE_DEFAULT
    try:
        doc = _figma_get(f"/files/{key}")
    except Exception as e:
        return jsonify({"error": f"Figma-Zugriff fehlgeschlagen: {e}"}), 400
    frames = []
    for page in doc.get("document", {}).get("children", []):
        for node in page.get("children", []):
            if node.get("type") in ("FRAME", "COMPONENT", "COMPONENT_SET", "GROUP"):
                frames.append({"id": node["id"], "name": node.get("name", ""), "page": page.get("name", "")})
    return jsonify({"name": doc.get("name"), "frames": frames})


@app.route("/figma/image")
def figma_image():
    if not figma_token():
        return jsonify({"error": "Kein Figma-Token hinterlegt."}), 400
    key = request.args.get("file") or FIGMA_FILE_DEFAULT
    ids = request.args.get("ids", "")
    fmt = request.args.get("format", "png")
    try:
        res = _figma_get(f"/images/{key}?ids={urllib.parse.quote(ids)}&format={fmt}&scale=2")
        return jsonify(res)  # {"images": {node_id: url}}
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/cv-pdf", methods=["POST"])
def cv_pdf():
    """Daten (JSON) + optionales Foto + Design -> fertiger, designter Lebenslauf als PDF."""
    if not CHROME:
        return jsonify({"error": "Kein Chrome/Edge gefunden – PDF-Erzeugung nicht möglich."}), 400
    try:
        daten = json.loads(request.form.get("daten") or "{}")
    except Exception:
        return jsonify({"error": "Ungültige Daten."}), 400
    if not (daten.get("vorname") or daten.get("nachname")):
        return jsonify({"error": "Erst einen Lebenslauf erstellen, dann das Design."}), 400

    foto_uri = None
    foto = request.files.get("foto")
    if foto and foto.filename:
        mt = (foto.mimetype or "image/jpeg")
        foto_uri = f"data:{mt};base64," + base64.b64encode(foto.read()).decode("ascii")

    design = request.form.get("design") or "gruen"
    if design in DESIGNS:  # feste, schnelle HTML-Vorlage
        beruf = [improfy_block(daten)] + (daten.get("berufserfahrung") or [])
        html = render_template(DESIGNS[design], d=daten, beruf=beruf, foto=foto_uri, niveau=_niveau_txt, logo=LOGO_URI)
    elif design in VORLAGEN_BY_ID and claude_verfuegbar():  # find-hire Vorlage 1:1 nachbauen
        ref = os.path.join(VORLAGEN_DIR, VORLAGEN_BY_ID[design]["ref"])
        html = design_from_reference(daten, ref)
        html = html.replace("__FOTO__", foto_uri or PLACEHOLDER_FOTO)
    elif claude_verfuegbar():  # weitere Stile werden von Claude generiert
        html = design_via_claude(daten, design)
        html = html.replace("__FOTO__", foto_uri or PLACEHOLDER_FOTO)
    else:
        beruf = [improfy_block(daten)] + (daten.get("berufserfahrung") or [])
        html = render_template("cv_gruen.html", d=daten, beruf=beruf, foto=foto_uri, niveau=_niveau_txt, logo=LOGO_URI)
    pdf = html_to_pdf(html)
    name = f"{daten.get('vorname','')}_{daten.get('nachname','')}".strip("_") or "Lebenslauf"
    name = re.sub(r"\s+", "_", name) + "_Lebenslauf.pdf"
    return send_file(io.BytesIO(pdf), as_attachment=True, download_name=name, mimetype="application/pdf")


@app.route("/generate", methods=["POST"])
def generate():
    return xlsx_antwort(build_data(request.form))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print("\n  Improfy CV Web-App läuft.")
    print(f"  → Im Browser öffnen:  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
