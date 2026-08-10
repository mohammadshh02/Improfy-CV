#!/usr/bin/env python3
"""
Zugangsverwaltung
=================
Pro Stadt ein Passwort, dazu ein Admin-Zugang für die Nutzungs-Übersicht.

Passwörter liegen NUR als Hash in `daten/zugaenge.json` — dort steht nie ein
Klartext-Passwort. Angelegt und geändert werden Zugänge mit `verwalten.py`.
"""
import functools
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

HIER = os.path.dirname(os.path.abspath(__file__))

# Hash-Verfahren fest vorgeben statt Werkzeugs Standard zu nehmen: der ist
# scrypt, und das fehlt in manchen Python-Builds (u.a. dem System-Python auf
# macOS). pbkdf2 gibt es überall — sonst ließe sich ein auf dem Mac gesetztes
# Passwort auf dem Server nicht prüfen.
HASH_VERFAHREN = "pbkdf2:sha256:600000"

# Nach dieser Zeit ohne Aktivität ist die Anmeldung abgelaufen.
SITZUNGSDAUER = timedelta(hours=12)

# Ab so vielen Fehlversuchen von derselben IP ist Schluss (siehe nutzung.py).
MAX_FEHLVERSUCHE = 10
SPERRE_MINUTEN = 15


def _schreibbarer_ordner():
    """Erster Ordner, in den wir wirklich schreiben dürfen.

    Auf dem Server ist das `cv_system/daten`. Auf Serverless-Hostern (Vercel)
    ist das Projektverzeichnis schreibgeschützt, dort bleibt nur /tmp — die
    Daten sind dann allerdings flüchtig.
    """
    for kandidat in (os.environ.get("DATEN_DIR"), os.path.join(HIER, "daten"),
                     "/tmp/improfy-daten"):
        if not kandidat:
            continue
        try:
            os.makedirs(kandidat, exist_ok=True)
            probe = os.path.join(kandidat, ".schreibtest")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return kandidat
        except OSError:
            continue
    raise RuntimeError("Kein schreibbarer Datenordner gefunden (DATEN_DIR setzen).")


DATEN_DIR = _schreibbarer_ordner()
ZUGAENGE_DATEI = os.path.join(DATEN_DIR, "zugaenge.json")


# ------------------------------------------------------------------ Konfig-IO
def _leer():
    return {"staedte": {}, "admin": None}


def _lesen():
    try:
        with open(ZUGAENGE_DATEI, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return _leer()
    cfg.setdefault("staedte", {})
    cfg.setdefault("admin", None)
    return cfg


_zwischenspeicher = {"stand": None, "cfg": None}


def konfig():
    """Zugänge lesen, gecacht bis sich die Datei ändert.

    Der Vergleich über mtime+Größe sorgt dafür, dass ein `verwalten.py`-Aufruf
    sofort greift — ohne Neustart und in allen gunicorn-Workern gleichzeitig.
    """
    try:
        s = os.stat(ZUGAENGE_DATEI)
        stand = (s.st_mtime_ns, s.st_size)
    except OSError:
        stand = None
    if _zwischenspeicher["stand"] != stand or _zwischenspeicher["cfg"] is None:
        _zwischenspeicher["cfg"] = _lesen()
        _zwischenspeicher["stand"] = stand
    return _zwischenspeicher["cfg"]


def speichern(cfg):
    """Atomar schreiben, damit ein Absturz mittendrin die Zugänge nicht zerlegt."""
    tmp = ZUGAENGE_DATEI + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, ZUGAENGE_DATEI)
    _zwischenspeicher["stand"] = None


# ------------------------------------------------------------------ Städte
def schluessel(name):
    """"Köln" -> "koeln" — der interne, URL-taugliche Name einer Stadt."""
    text = (name or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def staedte():
    """Alle Städte als Liste [(schluessel, anzeigename)], alphabetisch."""
    eintraege = konfig().get("staedte") or {}
    return sorted(((k, v.get("name") or k.title()) for k, v in eintraege.items()),
                  key=lambda p: p[1].lower())


def stadt_name(schl):
    if schl == "admin":
        return "Admin"
    eintrag = (konfig().get("staedte") or {}).get(schl) or {}
    return eintrag.get("name") or (schl or "").title()


def stadt_anlegen(name, passwort):
    """Stadt anlegen oder Passwort einer bestehenden Stadt ersetzen."""
    schl = schluessel(name)
    if not schl:
        raise ValueError("Ungültiger Stadtname.")
    cfg = konfig()
    bestand = (cfg["staedte"].get(schl) or {})
    cfg["staedte"][schl] = {
        "name": name.strip(),
        "hash": generate_password_hash(passwort, method=HASH_VERFAHREN),
        "angelegt": bestand.get("angelegt") or _jetzt(),
        "geaendert": _jetzt(),
    }
    speichern(cfg)
    return schl


def stadt_loeschen(schl):
    cfg = konfig()
    if schl not in cfg["staedte"]:
        return False
    del cfg["staedte"][schl]
    speichern(cfg)
    return True


def admin_setzen(passwort):
    cfg = konfig()
    cfg["admin"] = {
        "hash": generate_password_hash(passwort, method=HASH_VERFAHREN),
        "geaendert": _jetzt(),
    }
    speichern(cfg)


def eingerichtet():
    """Gibt es überhaupt schon einen Zugang? Sonst ist die App unbenutzbar."""
    cfg = konfig()
    return bool(cfg.get("staedte")) or bool(cfg.get("admin"))


def _jetzt():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ Anmeldung
def pruefe(kennung, passwort):
    """Passwort prüfen. Gibt die Rolle zurück ("stadt"/"admin") oder None."""
    cfg = konfig()
    if kennung == "admin":
        eintrag, rolle = cfg.get("admin"), "admin"
    else:
        eintrag, rolle = (cfg.get("staedte") or {}).get(kennung), "stadt"
    if not eintrag or not eintrag.get("hash"):
        return None
    if not check_password_hash(eintrag["hash"], passwort or ""):
        return None
    return rolle


def anmelden(kennung, rolle):
    session.clear()
    session["kennung"] = kennung
    session["rolle"] = rolle
    session.permanent = True


def abmelden():
    session.clear()


def angemeldet():
    return bool(session.get("kennung"))


def kennung():
    return session.get("kennung")


def ist_admin():
    return session.get("rolle") == "admin"


def absender_ip():
    """Echte Client-IP — hinter nginx steht in remote_addr sonst nur 127.0.0.1."""
    weiter = request.headers.get("X-Forwarded-For", "")
    if weiter:
        return weiter.split(",")[0].strip()
    return request.remote_addr or "-"


def _will_json():
    """Erwartet der Aufrufer JSON? Dann darf die Antwort keine Login-Seite sein."""
    if request.accept_mimetypes.best == "application/json":
        return True
    if request.headers.get("X-Requested-With") == "fetch":
        return True
    # Die Oberfläche schickt ihre Aufrufe per fetch() als POST mit FormData.
    return request.method == "POST"


def nicht_angemeldet_antwort():
    if _will_json():
        return jsonify({"error": "Sitzung abgelaufen. Bitte neu anmelden.",
                        "neu_anmelden": True}), 401
    return redirect(url_for("login", weiter=request.full_path.rstrip("?")))


def nur_admin(f):
    """Dekorator für Seiten, die ausschließlich der Admin sehen darf."""
    @functools.wraps(f)
    def huelle(*a, **kw):
        if not angemeldet():
            return nicht_angemeldet_antwort()
        if not ist_admin():
            return redirect(url_for("index"))
        return f(*a, **kw)
    return huelle


# ------------------------------------------------------------------ Secret Key
def secret_key():
    """Signierschlüssel für die Sitzungs-Cookies.

    Muss über Neustarts UND über alle gunicorn-Worker hinweg identisch sein —
    ein pro Prozess zufällig erzeugter Schlüssel würde Leute scheinbar grundlos
    aus der Sitzung werfen, sobald sie auf einem anderen Worker landen.
    """
    aus_umgebung = (os.environ.get("FLASK_SECRET") or "").strip()
    if aus_umgebung:
        return aus_umgebung

    pfad = os.path.join(DATEN_DIR, "secret.key")
    try:
        with open(pfad, encoding="utf-8") as f:
            vorhanden = f.read().strip()
        if vorhanden:
            return vorhanden
    except OSError:
        pass

    neu = secrets.token_hex(32)
    try:
        # O_EXCL: Starten mehrere Worker gleichzeitig, gewinnt genau einer —
        # die anderen lesen dessen Schlüssel statt ihren eigenen zu schreiben.
        fd = os.open(pfad, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(neu)
        return neu
    except FileExistsError:
        with open(pfad, encoding="utf-8") as f:
            return f.read().strip() or neu
    except OSError:
        return neu
