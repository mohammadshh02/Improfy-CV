#!/usr/bin/env python3
"""
Rahmen auf jede Seite stempeln
==============================
Für Vorlagen, die auf JEDER Seite denselben Rahmen tragen — Kopfband, Foto,
Kontaktspalte, Randstreifen — und rechts daneben fließenden Text.

WARUM NICHT IN CSS
------------------
Vier Wege wurden durchprobiert, alle scheitern an Chromes Druckausgabe:

1. `position:fixed` + `@page{margin:0}`
   Rahmen sitzt korrekt und wiederholt sich. Aber der Textfluss klebt dann ab
   Seite 2 am Papierrand, weil sich ein Einzug nach oben nicht pro Seite
   wiederholen lässt.
2. `position:fixed` + `@page` mit Rändern
   Chrome bezieht `fixed` auf den SATZSPIEGEL, nicht aufs Papier, und schneidet
   alles links davon ab. Mit Gegenrechnung verschiebt sich der Rahmen pro Seite.
3. `<thead>` als Abstandszeile
   Wiederholt sich nicht verlässlich; eine Zelle ohne sichtbaren Inhalt fällt
   zusammen, und der Einzug fehlt ab Seite 2.
4. Rahmen als `html`-Hintergrundkachel
   Die Kachel läuft durchs Dokument statt pro Seite — ab Seite 2 driftet sie.

DER WEG, DER FUNKTIONIERT
-------------------------
Chrome macht nur, was es gut kann: Text umbrechen. Der Inhalt wird mit
`@page`-Rändern gesetzt (die wirken zuverlässig auf jeder Seite), der Rahmen
einmal als eigene A4-Seite gerendert und anschließend UNTER jede Seite des
Inhalts gestempelt. Ergebnis: millimetergenau und auf jeder Seite identisch.
"""
import io

# PyMuPDF meldet sich je nach Version als fitz oder pymupdf.
try:
    import pymupdf
except ImportError:  # ältere Installationen
    import fitz as pymupdf


def stemple(inhalt_pdf, rahmen_pdf):
    """Rahmen (einseitiges PDF) unter jede Seite des Inhalts legen.

    „Unter" ist wichtig: mit overlay=False bleibt der Text oben und wird von
    farbigen Flächen des Rahmens nicht verdeckt.
    """
    inhalt = pymupdf.open(stream=inhalt_pdf, filetype="pdf")
    rahmen = pymupdf.open(stream=rahmen_pdf, filetype="pdf")
    if rahmen.page_count == 0:
        return inhalt_pdf
    try:
        for seite in inhalt:
            seite.show_pdf_page(seite.rect, rahmen, 0, overlay=False)
        puffer = io.BytesIO()
        inhalt.save(puffer)
        return puffer.getvalue()
    finally:
        inhalt.close()
        rahmen.close()


def seitenzahl(pdf_bytes):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return doc.page_count
    finally:
        doc.close()


def textraender(pdf_bytes):
    """Für Tests: je Seite (oben, unten) in mm, wo Text tatsächlich steht.

    Damit lässt sich nachmessen statt vermuten, ob eine Vorlage in den
    Papierrand läuft.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        ergebnis = []
        for seite in doc:
            bloecke = seite.get_text("blocks")
            if not bloecke:
                ergebnis.append(None)
                continue
            oben = min(b[1] for b in bloecke) / 72 * 25.4
            unten = max(b[3] for b in bloecke) / 72 * 25.4
            ergebnis.append((round(oben, 1), round(unten, 1)))
        return ergebnis
    finally:
        doc.close()
