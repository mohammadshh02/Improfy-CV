# Improfy CV Web-App

Mitarbeiter tippen die Lebenslauf-Infos in ein Browser-Formular →
die CV-Vorlage (Muster) wird automatisch ausgefüllt →
fertige, **kopier- und bearbeitbare** Excel zum Download.

## Starten
Doppelklick auf **`CV-App starten.command`** (liegt auf dem Schreibtisch und in `cv_system/`).
Der Browser öffnet sich automatisch auf **http://localhost:8000**.

Alternativ im Terminal:
```bash
cd ~/Desktop/Improfy/cv_system
python3 server.py        # dann http://localhost:8000 öffnen
```

## Benutzen
1. Grunddaten ausfüllen (Name, Geschlecht → für „Teilnehmer/in", Job, Kontakt, Führerschein).
2. Mit **„+ hinzufügen"** beliebig viele Stationen / Abschlüsse / Sprachen / Skills anlegen.
   Tätigkeiten: eine pro Zeile.
3. Unten **„Excel erstellen & herunterladen"** → fertige `Vorname_Nachname.xlsx`.

Das Ergebnis:
- 1:1 Muster-Optik, schwarze Datenschrift (Gr. 12)
- **keine verbundenen Zellen, kein Schutz** → frei in Excel kopier- und bearbeitbar
- fehlende Pflichtfelder gelb markiert + Checkliste (Spalte H)

## Für mehrere Mitarbeiter (im Netzwerk)
Läuft die App auf einem Rechner, können andere im gleichen WLAN über
`http://<IP-des-Rechners>:8000` zugreifen (die IP zeigt das Terminal beim Start).
Für dauerhaften/externen Betrieb bräuchte es später ein Hosting (z.B. kleiner Server).

## Technik
- `server.py` – Flask-Web-App (Formular → Excel)
- `templates/form.html` – das Eingabeformular
- `fill_cv.py` – Füll-/Style-Logik (gemeinsam mit dem Skript-Weg)
- `vorlagen/Muster-Vorlage.xlsx` – schlanke Vorlage (nur „Muster", schnelles Erzeugen)

## Nächste Ausbaustufen (optional)
- CV-PDF hochladen → KI liest aus → Formular vorausgefüllt (braucht API-Schlüssel)
- Speichern aller Kandidaten in einer Sammel-Mappe
- Login für Mitarbeiter / Hosting im Web


## 🪄 Schnell-Modus (KI): alle Infos reinwerfen
Ganz oben im Formular ist ein gelber Bereich. Dort **alles unsortiert reinschreiben ODER ein CV-PDF hochladen**
→ „Automatisch ausfüllen" → die KI sortiert die Infos ins Formular. Danach prüfen & „Excel erstellen".

**Einmalig aktivieren:** Anthropic-API-Schlüssel in die Datei `cv_system/.env` eintragen:
```
ANTHROPIC_API_KEY=sk-ant-...
```
Danach die App neu starten. Ohne Schlüssel funktioniert der manuelle Weg weiterhin voll.


## ✅ KI ohne API-Key – über Claude Code (Max-Abo)
Die App nutzt automatisch dein lokal installiertes **Claude Code** (Max-Abo) für die
KI-Sortierung (Text/PDF/Screenshot/Foto → Excel). **Kein separater API-Schlüssel nötig.**
- Voraussetzung: `claude` ist installiert und eingeloggt (ist es).
- Dauer pro CV: ca. 20–40 Sekunden.
- Optional: Trägt man in `.env` einen `ANTHROPIC_API_KEY` ein, nutzt die App stattdessen
  die schnellere API (wenige Sekunden, kostet ein paar Cent/CV).
