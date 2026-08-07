# Improfy CV-System – Anleitung

Du wirfst **beliebige/unsortierte Daten** (PDF oder Text) rein → die KI **sortiert
sie automatisch** an die richtige Stelle → fertige Excel in **1:1 Muster-Optik**,
inkl. Feedback, was noch fehlt.

## Das Prinzip

```
   Rohdaten (PDF / Text, egal wie unsortiert)
        │   ① KI sortiert automatisch
        ▼
   strukturierte Daten (JSON)
        │   ② füllt geklontes "Muster"
        ▼
   fertige Excel  (blaue Felder, gleiche Optik)  +  Feedback was fehlt
```

Die **Auto-Sortierung** macht die KI. Es gibt zwei Wege, sie zu nutzen:

---

## Weg A – Ich (Claude) sortiere  ← am einfachsten, kein Setup

1. Du schickst mir die Rohdaten (PDF, Foto, oder einfach hier reingetippt – egal
   wie durcheinander) über `rohdaten_vorlage.txt` oder direkt im Chat.
2. Ich erzeuge daraus die sortierte `kandidat.json`.
3. Du machst nur den letzten Schritt:
   ```bash
   cd ~/Desktop/Improfy/cv_system
   python3 fill_cv.py kandidat.json "ID-K0148_Max_Mustermann"
   ```

## Weg B – Alles automatisch per Skript  (einmal Setup)

**Einmalig:**
```bash
pip3 install anthropic openpyxl
export ANTHROPIC_API_KEY="sk-ant-..."      # deinen Schlüssel eintragen
```

**Dann pro Kandidat EIN Befehl:**
```bash
cd ~/Desktop/Improfy/cv_system
python3 cv.py "Lebenslauf.pdf"  "ID-K0148_Max_Mustermann"
# oder mit Textdatei:
python3 cv.py "rohdaten.txt"    "ID-K0148_Max_Mustermann"
```
Das macht Sortieren + Ausfüllen in einem Rutsch.

---

## Was am Ende rauskommt (pro Kandidat)

1. **Neuer Tab** in der Master-Mappe (`ID-Kxxxx_Name`) – 1:1 wie das „Muster"
   (blaue Schrift, graue Flächen, gleiches Layout, verbundene Zellen).
2. **Einzelne Excel** nur mit diesem Blatt → im Ordner `ausgabe/` – zum Weiterschicken.
3. **Feedback**: fehlende Pflichtfelder **gelb markiert** + Checkliste
   (Spalte H im Blatt + `..._CHECKLISTE.txt`).

## Rohdaten schnell erfassen
Öffne `rohdaten_vorlage.txt`, schreib alles rein was du weißt (Reihenfolge egal),
speichere z.B. als `max.txt` – fertig zum Reinwerfen.

## Dateien im System

| Datei | Zweck |
|---|---|
| `cv.py` | Alles-in-einem: Rohdaten → fertige Excel |
| `extract_cv.py` | KI sortiert Rohdaten (PDF/Text) → JSON |
| `fill_cv.py` | JSON → Excel (Tab + Einzel-Datei + Checkliste) |
| `schema.py` | Datenformat |
| `rohdaten_vorlage.txt` | Vorlage zum Reinwerfen roher Daten |
| `beispiel_sahar.json` | Beispiel-Datensatz |

## Optionen (fill_cv.py & cv.py)
```bash
--master "/Pfad/zur/Master.xlsx"   # andere Master-Mappe
--out    "/Pfad/zum/Ausgabeordner" # anderer Ausgabeordner
```
Standard-Master: `~/Desktop/Improfy/Sahar Mohammadi Niyay Rodsary.xlsx`

## Pflichtfelder (→ gelb, wenn leer)
Vorname, Nachname, Angestrebter Job, Geburtsdatum, Mobil, E-Mail, Adresse,
mind. 1 Berufserfahrung, mind. 1 Bildung, Deutsch, Über-mich, Foto-Link, Hobbys.

## Hinweise
- KI-Tätigkeiten & abgeleitete Soft Skills bitte gegenlesen (branchenüblich ergänzt).
- Gleicher Blattname erneut = altes Blatt wird ersetzt (kein Duplikat).
- Vorm ersten Lauf ggf. ein Backup der Master-Datei anlegen.
