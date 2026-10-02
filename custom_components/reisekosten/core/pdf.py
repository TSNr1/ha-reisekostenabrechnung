"""PDF-Ausgabe der Abrechnung (reportlab). Layout angelehnt an die Onexma-Abrechnung."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from .engine import Statement, fmt_money

W, H = A4
LEFT = 20 * mm
RIGHT = W - 8.5 * mm
COL2 = 113 * mm
GRAY = colors.HexColor("#b4b4b4")
LIGHT = colors.HexColor("#ececec")

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=11.5)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10)
RIGHT_ALIGNED = ParagraphStyle("right", parent=BODY, alignment=2)


def _top(mm_from_top: float) -> float:
    return H - mm_from_top * mm


def _lines(c: canvas.Canvas, x: float, y_mm: float, lines: list[str], size=10, pitch=4.7):
    c.setFont("Helvetica", size)
    for i, text in enumerate(lines):
        c.drawString(x, _top(y_mm + i * pitch), text)


def _footer(c: canvas.Canvas, st: Statement, page: int, pages: int) -> None:
    m = st.meta
    c.setStrokeColor(colors.HexColor("#999999"))
    c.setLineWidth(0.4)
    c.line(LEFT, _top(275.5), RIGHT, _top(275.5))
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    c.drawString(LEFT, _top(279), f"Abrechnung Nr. {m.number}  Benutzer: {m.user}")
    paid = "ja" if st.days else "nein"
    for i, text in enumerate((f"Status: {m.status}",
                              f"Pauschalen abrechnen: {paid}, Tage: {st.calendar_days}",
                              "Frühstücksregel: Pauschale")):
        c.drawString(COL2, _top(279 + i * 3.4), text)
    c.drawRightString(RIGHT, _top(279), f"{page} / {pages}")
    c.setFont("Helvetica", 7.5)
    c.drawRightString(RIGHT, _top(291.5), "Erstellt mit Home Assistant")


def _page_one(c: canvas.Canvas, st: Statement) -> None:
    m, trip = st.meta, st.trip
    _lines(c, LEFT, 22, [m.company, m.person, m.street, m.city])
    _lines(c, LEFT, 50, [m.company, m.street, m.city])

    c.setFont("Helvetica", 21)
    c.drawString(COL2, _top(18), "Reisekostenabrechnung")

    zeitraum = f"{trip.start:%d.%m.%Y %H:%M} - {trip.end:%d.%m.%Y %H:%M}"
    meta_rows = [("Zeitraum", zeitraum), ("Reise", m.trip_name), ("Zweck", m.purpose),
                 ("Land", st.rules.country), ("Strecke", m.route)]
    style = ParagraphStyle("meta", parent=BODY, fontSize=10, leading=13.2)
    y = 25.0
    for label, value in meta_rows:
        if not value:
            continue
        p = Paragraph(f"{label}: {value}", style)
        _, h = p.wrap(RIGHT - COL2, 100 * mm)
        p.drawOn(c, COL2, _top(y) - h)
        y += h / mm + 1.3

    # Tabelle
    data = [["Datum", "Art, Bezeichnung", "Netto", "Steuer", "Brutto"]]
    for line in st.lines:
        text = line.text if not line.sub else f"{line.text}<br/>{line.sub}"
        data.append([line.day.strftime("%d.%m.%y"), Paragraph(text, BODY),
                     fmt_money(line.net), "", fmt_money(line.gross)])
    data.append(["", "Summe", fmt_money(st.total), "", fmt_money(st.total)])

    widths = [16 * mm, 102.5 * mm, 22.5 * mm, 18 * mm, 22.5 * mm]
    table = Table(data, colWidths=widths)
    ts = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), GRAY),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#555555")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), LIGHT),
    ]
    for r in range(2, len(data) - 1, 2):
        ts.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    table.setStyle(TableStyle(ts))
    _, th = table.wrap(RIGHT - LEFT, 200 * mm)
    top = 85 * mm
    table.drawOn(c, LEFT, _top(top / mm) - th)

    below = top + th
    c.setFont("Helvetica-Bold", 10)
    c.drawString(COL2, _top(below / mm + 7), "Reisekosten")
    c.drawRightString(RIGHT, _top(below / mm + 7), fmt_money(st.total))

    # Notizen
    note = m.note or f"{m.user}, {datetime.now():%d.%m.%Y %H:%M}: Abrechnung erstellt"
    box_top = below / mm + 4
    c.setDash(1, 1.5)
    c.setStrokeColor(colors.HexColor("#777777"))
    c.rect(LEFT, _top(box_top + 16), 87 * mm, 16 * mm)
    c.setDash()
    c.setFont("Helvetica", 10)
    c.drawString(LEFT + 1.5 * mm, _top(box_top + 4.5), "Notizen")
    p = Paragraph(note, BODY)
    _, ph = p.wrap(84 * mm, 12 * mm)
    p.drawOn(c, LEFT + 1.5 * mm, _top(box_top + 9) - ph)


def _page_two(c: canvas.Canvas, st: Statement) -> None:
    c.setFont("Helvetica-Bold", 12)
    c.drawString(LEFT, _top(25), f"Buchungsliste Abrechnung {st.meta.number}")
    head = ["Unterart", "Zahlweise", "Steuer", "Konto", "Gegenkonto", "Währung", "Brutto", "Steuer", "Netto"]
    rows = [head]

    def num(v):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    for b in st.bookings:
        rows.append([b.label, b.payment, b.tax_rate, b.account, b.contra, "EUR",
                     num(b.gross), num(b.tax), num(b.net)])
    tot = sum((b.gross for b in st.bookings), st.total * 0)
    rows.append(["Summen", "", "", "", "", "EUR", num(tot), num(sum((b.tax for b in st.bookings), tot * 0)),
                 num(sum((b.net for b in st.bookings), tot * 0))])
    cell = ParagraphStyle("cell", parent=BODY, fontSize=8, leading=9.5)
    rows = [[Paragraph(x, cell) if isinstance(x, str) and i else x for x in r] for i, r in enumerate(rows)]
    table = Table(rows, colWidths=[40 * mm, 18 * mm, 13 * mm, 15 * mm, 22 * mm, 16 * mm, 19 * mm, 15 * mm, 19 * mm])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("BACKGROUND", (0, 0), (-1, 0), GRAY),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#555555")),
        ("ALIGN", (6, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), LIGHT),
    ]))
    _, th = table.wrap(RIGHT - LEFT, 100 * mm)
    table.drawOn(c, LEFT, _top(32) - th)


def render_pdf(st: Statement, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"Reisekostenabrechnung {st.meta.number}".strip())
    c.setAuthor(st.meta.person)
    pages = 2 if st.bookings else 1
    _page_one(c, st)
    _footer(c, st, 1, pages)
    if st.bookings:
        c.showPage()
        _page_two(c, st)
        _footer(c, st, 2, pages)
    c.save()
    return path
