#!/usr/bin/env python3
"""
Zugänge verwalten (Kommandozeile)
=================================
Wird direkt auf dem Server ausgeführt — Passwörter werden nie über die Web-App
gesetzt und tauchen nirgends im Klartext auf.

    python3 verwalten.py liste
    python3 verwalten.py stadt "Köln"          # anlegen / Passwort ändern
    python3 verwalten.py stadt "Köln" --zufall # Passwort erzeugen lassen
    python3 verwalten.py admin
    python3 verwalten.py loeschen koeln

Änderungen greifen sofort, ein Neustart der App ist nicht nötig.
"""
import getpass
import secrets
import string
import sys

import zugang

# Ohne l/I/1/0/O — die werden beim Weitergeben zu oft falsch abgetippt.
ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "lI1O0")


def zufallspasswort(laenge=14):
    return "".join(secrets.choice(ALPHABET) for _ in range(laenge))


def passwort_abfragen():
    while True:
        eins = getpass.getpass("Passwort: ")
        if len(eins) < 8:
            print("  Mindestens 8 Zeichen, bitte nochmal.")
            continue
        if eins != getpass.getpass("Wiederholen: "):
            print("  Stimmt nicht überein, bitte nochmal.")
            continue
        return eins


def cmd_liste():
    staedte = zugang.staedte()
    if not staedte:
        print("Noch keine Stadt angelegt.")
    else:
        print(f"{len(staedte)} Stadt-Zugänge:")
        for schl, name in staedte:
            print(f"  {schl:<20} {name}")
    print("Admin-Zugang:", "eingerichtet" if zugang.konfig().get("admin") else "FEHLT")
    print("Daten liegen in:", zugang.DATEN_DIR)


def cmd_stadt(argumente):
    if not argumente:
        print("Name fehlt:  verwalten.py stadt \"Köln\"")
        return 1
    zufall = "--zufall" in argumente
    name = " ".join(a for a in argumente if a != "--zufall").strip()
    if not name:
        print("Name fehlt.")
        return 1

    schl = zugang.schluessel(name)
    vorhanden = schl in (zugang.konfig().get("staedte") or {})
    print(f"{'Passwort ändern für' if vorhanden else 'Neu anlegen:'} {name}  (Kürzel: {schl})")

    passwort = zufallspasswort() if zufall else passwort_abfragen()
    zugang.stadt_anlegen(name, passwort)
    print(f"✓ {name} gespeichert.")
    if zufall:
        print(f"\n  Zugang für {name}\n  Passwort: {passwort}\n")
        print("  Einmal notieren — es lässt sich später nicht mehr auslesen,")
        print("  gespeichert wird nur der Hash.")
    return 0


def cmd_admin():
    vorhanden = bool(zugang.konfig().get("admin"))
    print("Admin-Passwort " + ("ändern" if vorhanden else "setzen"))
    zugang.admin_setzen(passwort_abfragen())
    print("✓ Admin-Zugang gespeichert. Anmelden mit der Auswahl 'Admin'.")
    return 0


def cmd_loeschen(argumente):
    if not argumente:
        print("Kürzel fehlt:  verwalten.py loeschen koeln")
        return 1
    schl = zugang.schluessel(argumente[0])
    if zugang.stadt_loeschen(schl):
        print(f"✓ {schl} gelöscht. Bereits angemeldete Sitzungen laufen aus.")
        return 0
    print(f"Kein Zugang mit dem Kürzel {schl}.")
    return 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "hilfe"):
        print(__doc__)
        return 0
    befehl, rest = argv[0], argv[1:]
    if befehl == "liste":
        cmd_liste()
        return 0
    if befehl == "stadt":
        return cmd_stadt(rest)
    if befehl == "admin":
        return cmd_admin()
    if befehl == "loeschen":
        return cmd_loeschen(rest)
    print(f"Unbekannter Befehl: {befehl}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
