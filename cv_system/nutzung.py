#!/usr/bin/env python3
"""
Nutzungs-Protokoll
==================
Hält fest, welche Stadt wann was gemacht hat — als Grundlage für das
Admin-Panel.

BEWUSST OHNE KUNDENDATEN: protokolliert werden nur Stadt, Aktion, Zeitpunkt,
Erfolg und Dauer. Keine Namen, keine Inhalte, keine Dateinamen. Wer welchen
Lebenslauf erstellt hat, lässt sich hieraus also nicht ablesen — das ist so
gewollt (DSGVO-Datensparsamkeit).

SQLite statt Logdatei, weil die drei gunicorn-Worker parallel schreiben und das
Admin-Panel sonst jedes Mal die ganze Datei durchrechnen müsste.
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import zugang

DB_DATEI = os.path.join(zugang.DATEN_DIR, "nutzung.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ereignisse (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit     TEXT    NOT NULL,          -- ISO 8601, UTC
    stadt    TEXT    NOT NULL,          -- Schlüssel der Stadt, "admin" oder "-"
    aktion   TEXT    NOT NULL,
    status   TEXT    NOT NULL DEFAULT 'ok',
    dauer_ms INTEGER,
    ip       TEXT
);
CREATE INDEX IF NOT EXISTS idx_ereignisse_zeit  ON ereignisse(zeit);
CREATE INDEX IF NOT EXISTS idx_ereignisse_stadt ON ereignisse(stadt, zeit);
"""

# Aktionen, die gezählt werden. Die Beschriftungen tauchen im Admin-Panel auf.
AKTIONEN = {
    "lebenslauf":    "Lebenslauf (Excel)",
    "pdf_design":    "PDF-Design",
    "ki_auswertung": "KI-Auswertung",
    "login":         "Anmeldung",
    "login_fehler":  "Fehlversuch",
}
# Was als „Nutzung" gilt — Anmeldungen sind kein Arbeitsergebnis.
ARBEIT = ("lebenslauf", "pdf_design", "ki_auswertung")


def _verbindung():
    con = sqlite3.connect(DB_DATEI, timeout=10)
    con.row_factory = sqlite3.Row
    # WAL: Lesen (Admin-Panel) blockiert Schreiben (laufende CVs) nicht.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def init():
    with _verbindung() as con:
        con.executescript(SCHEMA)


def _jetzt():
    return datetime.now(timezone.utc)


def protokolliere(stadt, aktion, status="ok", dauer_ms=None, ip=None):
    """Ein Ereignis festhalten.

    Schlägt das fehl, wird es auf stderr gemeldet (landet im journal), aber
    nie durchgereicht: ein kaputtes Protokoll darf niemandem die Excel zerreißen.
    """
    try:
        with _verbindung() as con:
            con.execute(
                "INSERT INTO ereignisse (zeit, stadt, aktion, status, dauer_ms, ip)"
                " VALUES (?,?,?,?,?,?)",
                (_jetzt().isoformat(timespec="seconds"), stadt or "-", aktion,
                 status, dauer_ms, ip),
            )
    except sqlite3.Error as e:
        print(f"[nutzung] Protokoll fehlgeschlagen ({aktion}): {e}", file=sys.stderr)


def _grenze(tage=None, minuten=None):
    delta = timedelta(days=tage or 0, minutes=minuten or 0)
    return (_jetzt() - delta).isoformat(timespec="seconds")


# ------------------------------------------------------------- Login-Bremse
def zu_viele_fehlversuche(ip):
    """Bremst Passwort-Raten aus. Zählt über alle Worker hinweg, weil in der DB."""
    if not ip or ip == "-":
        return False
    try:
        with _verbindung() as con:
            anzahl = con.execute(
                "SELECT COUNT(*) FROM ereignisse"
                " WHERE aktion='login_fehler' AND ip=? AND zeit>=?",
                (ip, _grenze(minuten=zugang.SPERRE_MINUTEN)),
            ).fetchone()[0]
    except sqlite3.Error:
        return False   # Im Zweifel durchlassen statt alle aussperren.
    return anzahl >= zugang.MAX_FEHLVERSUCHE


# ------------------------------------------------------------- Auswertungen
def fehlversuche_je_ip(stunden=24, limit=5):
    """Woher kamen falsche Passwörter — [(ip, anzahl)], häufigste zuerst."""
    try:
        with _verbindung() as con:
            zeilen = con.execute(
                "SELECT ip, COUNT(*) FROM ereignisse"
                " WHERE aktion='login_fehler' AND zeit>=? AND ip IS NOT NULL"
                " GROUP BY ip ORDER BY 2 DESC LIMIT ?",
                (_grenze(minuten=stunden * 60), limit),
            ).fetchall()
    except sqlite3.Error:
        return []
    return [(z[0], z[1]) for z in zeilen]


def anmeldungen(stunden=24):
    """Erfolgreiche und fehlgeschlagene Anmeldungen im Zeitraum."""
    try:
        with _verbindung() as con:
            z = con.execute(
                "SELECT SUM(aktion='login') AS ok, SUM(aktion='login_fehler') AS fehler"
                " FROM ereignisse WHERE zeit>=?",
                (_grenze(minuten=stunden * 60),),
            ).fetchone()
    except sqlite3.Error:
        return {"ok": 0, "fehler": 0}
    return {"ok": z["ok"] or 0, "fehler": z["fehler"] or 0}


def uebersicht(tage=30):
    """Pro Stadt: wie viel, wovon, und wann zuletzt."""
    seit = _grenze(tage=tage)
    with _verbindung() as con:
        zeilen = con.execute(
            """
            SELECT stadt,
                   SUM(aktion='lebenslauf')                    AS lebenslaeufe,
                   SUM(aktion='pdf_design')                    AS designs,
                   SUM(aktion='ki_auswertung')                 AS ki,
                   SUM(aktion='login')                         AS logins,
                   SUM(status!='ok' AND aktion!='login_fehler') AS fehler,
                   MAX(zeit)                                   AS zuletzt
              FROM ereignisse
             WHERE zeit >= ? AND stadt NOT IN ('-','admin')
             GROUP BY stadt
            """,
            (seit,),
        ).fetchall()

    ergebnis = []
    for z in zeilen:
        gesamt = (z["lebenslaeufe"] or 0) + (z["designs"] or 0) + (z["ki"] or 0)
        ergebnis.append({
            "stadt": z["stadt"],
            "name": zugang.stadt_name(z["stadt"]),
            "lebenslaeufe": z["lebenslaeufe"] or 0,
            "designs": z["designs"] or 0,
            "ki": z["ki"] or 0,
            "logins": z["logins"] or 0,
            "fehler": z["fehler"] or 0,
            "gesamt": gesamt,
            "zuletzt": z["zuletzt"],
        })

    # Städte ohne jede Aktivität sollen trotzdem auftauchen — gerade die sind
    # ja die interessante Information ("nutzt es keiner").
    bekannt = {e["stadt"] for e in ergebnis}
    for schl, name in zugang.staedte():
        if schl not in bekannt:
            ergebnis.append({"stadt": schl, "name": name, "lebenslaeufe": 0,
                             "designs": 0, "ki": 0, "logins": 0, "fehler": 0,
                             "gesamt": 0, "zuletzt": None})
    ergebnis.sort(key=lambda e: (-e["gesamt"], e["name"].lower()))
    return ergebnis


def verlauf(tage=30):
    """Arbeits-Aktionen pro Tag und Stadt, für den Balkenverlauf im Panel."""
    seit = _grenze(tage=tage)
    platzhalter = ",".join("?" * len(ARBEIT))
    with _verbindung() as con:
        zeilen = con.execute(
            f"""
            SELECT substr(zeit,1,10) AS tag, stadt, COUNT(*) AS anzahl
              FROM ereignisse
             WHERE zeit >= ? AND aktion IN ({platzhalter}) AND status='ok'
             GROUP BY tag, stadt
            """,
            (seit, *ARBEIT),
        ).fetchall()

    je_tag = {}
    for z in zeilen:
        eintrag = je_tag.setdefault(z["tag"], {"tag": z["tag"], "gesamt": 0, "je_stadt": {}})
        eintrag["je_stadt"][z["stadt"]] = z["anzahl"]
        eintrag["gesamt"] += z["anzahl"]

    # Tage ohne Nutzung müssen als Lücke sichtbar sein, nicht einfach fehlen.
    heute = _jetzt().date()
    reihe = []
    for rueck in range(tage - 1, -1, -1):
        tag = (heute - timedelta(days=rueck)).isoformat()
        reihe.append(je_tag.get(tag, {"tag": tag, "gesamt": 0, "je_stadt": {}}))
    return reihe


def letzte(limit=80):
    """Die jüngsten Ereignisse für die Detailliste."""
    with _verbindung() as con:
        # Nach Zeit sortieren, nicht nach id: die id folgt der Einfüge-Reihenfolge,
        # und bei parallelen Workern ist die nicht zwingend chronologisch.
        zeilen = con.execute(
            "SELECT zeit, stadt, aktion, status, dauer_ms, ip FROM ereignisse"
            " ORDER BY zeit DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [{
        "zeit": z["zeit"],
        "stadt": z["stadt"],
        "name": zugang.stadt_name(z["stadt"]) if z["stadt"] not in ("-",) else "—",
        "aktion": z["aktion"],
        "aktion_text": AKTIONEN.get(z["aktion"], z["aktion"]),
        "status": z["status"],
        "dauer_ms": z["dauer_ms"],
        "ip": z["ip"],
    } for z in zeilen]


def summen(tage=30):
    """Kennzahlen für die Kacheln oben im Panel."""
    seit = _grenze(tage=tage)
    platzhalter = ",".join("?" * len(ARBEIT))
    with _verbindung() as con:
        z = con.execute(
            f"""
            SELECT SUM(aktion='lebenslauf')    AS lebenslaeufe,
                   SUM(aktion='pdf_design')    AS designs,
                   SUM(aktion='ki_auswertung') AS ki,
                   SUM(aktion='login_fehler')  AS fehlversuche,
                   COUNT(DISTINCT CASE WHEN aktion IN ({platzhalter})
                                       THEN stadt END)          AS aktive_staedte,
                   AVG(CASE WHEN aktion='ki_auswertung' AND status='ok'
                            THEN dauer_ms END)                  AS ki_schnitt
              FROM ereignisse WHERE zeit >= ?
            """,
            (*ARBEIT, seit),
        ).fetchone()
    return {
        "lebenslaeufe": z["lebenslaeufe"] or 0,
        "designs": z["designs"] or 0,
        "ki": z["ki"] or 0,
        "fehlversuche": z["fehlversuche"] or 0,
        "aktive_staedte": z["aktive_staedte"] or 0,
        "ki_schnitt_s": round((z["ki_schnitt"] or 0) / 1000, 1) if z["ki_schnitt"] else None,
    }
