#!/usr/bin/env python3
"""
Systembericht
=============
Sammelt einmal täglich per Cron den Zustand von Dienst, Logs und Maschine
und hängt ihn an `daten/tagesbericht.log` an. Läuft auch dann weiter, wenn
niemand hinschaut — die Kennzahlen tauchen zusätzlich im Admin-Panel auf.

    python3 systembericht.py          # Bericht schreiben und ausgeben
    python3 systembericht.py --still  # nur schreiben (fuer Cron)

Der Cron-Auftrag läuft als root, weil `journalctl -u improfy` sonst nicht
lesbar ist. Alles, was die Web-App selbst berechnen kann (Platte, Speicher,
Fehlversuche), holt sie sich live — der Bericht liefert nur die Teile,
für die es Root-Rechte braucht.
"""
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

import nutzung  # noqa: E402
import zugang  # noqa: E402

BERICHT_DATEI = os.path.join(zugang.DATEN_DIR, "tagesbericht.log")
MAX_ZEILEN = 1200          # ~100 Berichte, danach fallen die aeltesten raus

# Schwellen, ab denen ein Bericht als auffaellig gilt
PLATTE_WARNUNG = 85        # Prozent belegt
SPEICHER_WARNUNG = 10      # Prozent frei
FEHLVERSUCHE_WARNUNG = 10  # von derselben IP innerhalb 24 h


def _ruf(*befehl):
    """Kommando ausfuehren, im Fehlerfall None statt Absturz."""
    try:
        return subprocess.run(befehl, capture_output=True, text=True,
                              timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def dienst():
    roh = _ruf("systemctl", "show", "improfy",
               "-p", "ActiveState", "-p", "NRestarts", "-p", "ActiveEnterTimestamp")
    werte = {}
    for zeile in (roh or "").splitlines():
        if "=" in zeile:
            k, v = zeile.split("=", 1)
            werte[k] = v
    return {
        "zustand": werte.get("ActiveState") or "unbekannt",
        "neustarts": int(werte.get("NRestarts") or 0),
        "seit": werte.get("ActiveEnterTimestamp") or "unbekannt",
    }


def journal(stunden=24):
    """Tracebacks und Serverfehler im Journal zaehlen."""
    roh = _ruf("journalctl", "-u", "improfy", "--since", f"{stunden} hours ago",
               "--no-pager", "--output=cat")
    if roh is None:
        return {"lesbar": False, "tracebacks": 0, "serverfehler": 0}
    tracebacks = len(re.findall(r"traceback|exception", roh, re.I))
    # Zugriffszeilen sehen aus wie: "GET /x HTTP/1.0" 500 123
    serverfehler = len(re.findall(r'"\s5\d{2}\s', roh))
    return {"lesbar": True, "tracebacks": tracebacks, "serverfehler": serverfehler}


def platte():
    gesamt, benutzt, frei = shutil.disk_usage("/")
    return {"gesamt_gb": gesamt / 1e9, "benutzt_gb": benutzt / 1e9,
            "prozent": round(benutzt / gesamt * 100) if gesamt else 0}


def speicher():
    """Aus /proc/meminfo — auf macOS (Entwicklung) gibt es das nicht."""
    try:
        werte = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for zeile in f:
                teile = zeile.split()
                if len(teile) >= 2:
                    werte[teile[0].rstrip(":")] = int(teile[1])   # kB
        gesamt, verfuegbar = werte.get("MemTotal", 0), werte.get("MemAvailable", 0)
        if not gesamt:
            return None
        return {"gesamt_gb": gesamt / 1e6, "frei_gb": verfuegbar / 1e6,
                "prozent_frei": round(verfuegbar / gesamt * 100)}
    except OSError:
        return None


def sammle(stunden=24):
    daten = {
        "zeit": datetime.now(timezone.utc),
        "dienst": dienst(),
        "journal": journal(stunden),
        "platte": platte(),
        "speicher": speicher(),
        "nutzung": nutzung.summen(1),
        "fehl_ips": nutzung.fehlversuche_je_ip(stunden=stunden),
        "anmeldungen": nutzung.anmeldungen(stunden=stunden),
    }
    daten["auffaellig"] = auffaelligkeiten(daten)
    return daten


def auffaelligkeiten(d):
    """Was jemand wissen muss, ohne den ganzen Bericht zu lesen."""
    treffer = []
    if d["dienst"]["zustand"] != "active":
        treffer.append(f"Dienst ist {d['dienst']['zustand']}, nicht active")
    if d["dienst"]["neustarts"]:
        treffer.append(f"{d['dienst']['neustarts']} unerwartete Neustarts seit dem Start")
    if d["journal"]["tracebacks"]:
        treffer.append(f"{d['journal']['tracebacks']} Tracebacks im Journal")
    if d["journal"]["serverfehler"]:
        treffer.append(f"{d['journal']['serverfehler']} Serverfehler (5xx)")
    for ip, anzahl in d["fehl_ips"]:
        if anzahl >= FEHLVERSUCHE_WARNUNG:
            treffer.append(f"{anzahl} Anmeldeversuche von {ip}")
    if d["platte"]["prozent"] >= PLATTE_WARNUNG:
        treffer.append(f"Platte zu {d['platte']['prozent']}% belegt")
    if d["speicher"] and d["speicher"]["prozent_frei"] <= SPEICHER_WARNUNG:
        treffer.append(f"nur noch {d['speicher']['prozent_frei']}% Arbeitsspeicher frei")
    return treffer


def als_text(d):
    zeilen = [f"=== {d['zeit'].strftime('%Y-%m-%d %H:%M')} UTC ==="]
    if d["auffaellig"]:
        zeilen.append("Zustand: ACHTUNG - " + "; ".join(d["auffaellig"]))
    else:
        zeilen.append("Zustand: ok")

    dn = d["dienst"]
    zeilen.append(f"Dienst: {dn['zustand']}, {dn['neustarts']} Neustarts, seit {dn['seit']}")

    j = d["journal"]
    zeilen.append("Journal (24h): " + (
        f"{j['tracebacks']} Tracebacks, {j['serverfehler']} Serverfehler"
        if j["lesbar"] else "nicht lesbar (fehlende Rechte)"))

    a = d["anmeldungen"]
    zeilen.append(f"Anmeldungen (24h): {a['ok']} erfolgreich, {a['fehler']} fehlgeschlagen")
    if d["fehl_ips"]:
        zeilen.append("  Fehlversuche je IP: " +
                      ", ".join(f"{ip} ({n}x)" for ip, n in d["fehl_ips"]))

    n = d["nutzung"]
    zeilen.append(f"Nutzung (24h): {n['lebenslaeufe']} Lebenslaeufe, "
                  f"{n['designs']} Designs, {n['ki']} KI-Auswertungen")

    p = d["platte"]
    zeilen.append(f"Platte: {p['benutzt_gb']:.1f} von {p['gesamt_gb']:.0f} GB ({p['prozent']}%)")
    if d["speicher"]:
        s = d["speicher"]
        zeilen.append(f"Speicher: {s['frei_gb']:.1f} von {s['gesamt_gb']:.1f} GB frei "
                      f"({s['prozent_frei']}%)")
    return "\n".join(zeilen)


def schreibe(text):
    alt = ""
    try:
        with open(BERICHT_DATEI, encoding="utf-8") as f:
            alt = f.read()
    except OSError:
        pass
    zeilen = (alt + text + "\n\n").splitlines()
    if len(zeilen) > MAX_ZEILEN:                 # aelteste Bloecke abschneiden
        zeilen = zeilen[-MAX_ZEILEN:]
    with open(BERICHT_DATEI, "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen) + "\n")
    try:
        os.chmod(BERICHT_DATEI, 0o640)           # root schreibt, die App liest
        import grp
        os.chown(BERICHT_DATEI, os.stat(BERICHT_DATEI).st_uid,
                 grp.getgrnam("improfy").gr_gid)
    except (OSError, KeyError, ImportError):
        pass


def letzter_bericht():
    """Den jüngsten Block fürs Admin-Panel — None, wenn noch keiner existiert."""
    try:
        with open(BERICHT_DATEI, encoding="utf-8") as f:
            inhalt = f.read().strip()
        stand = datetime.fromtimestamp(os.path.getmtime(BERICHT_DATEI), timezone.utc)
    except OSError:
        return None
    if not inhalt:
        return None
    block = inhalt.split("=== ")[-1]
    zeilen = ("=== " + block).splitlines()
    zustand = next((z for z in zeilen if z.startswith("Zustand:")), "Zustand: unbekannt")
    return {
        "stand": stand.isoformat(timespec="seconds"),
        "ok": zustand.strip() == "Zustand: ok",
        "zustand": zustand.replace("Zustand:", "").strip(),
        "veraltet": datetime.now(timezone.utc) - stand > timedelta(days=2),
        "text": "\n".join(zeilen).strip(),
    }


def kennzahlen():
    """Was das Admin-Panel live anzeigt, ohne Root-Rechte zu brauchen."""
    return {
        "platte": platte(),
        "speicher": speicher(),
        "fehl_ips": nutzung.fehlversuche_je_ip(stunden=24 * 7),
        "bericht": letzter_bericht(),
    }


if __name__ == "__main__":
    bericht = als_text(sammle())
    schreibe(bericht)
    if "--still" not in sys.argv:
        print(bericht)
