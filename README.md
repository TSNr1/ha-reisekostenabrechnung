<p align="center"><img src="docs/icon.png" width="128" alt="Reisekosten"></p>

# Reisekosten für Home Assistant

Erstellt automatisch eine Reisekostenabrechnung (PDF) für jede Reise: Die Integration beobachtet eine `person`-Entität.
Verlässt sie die Heimzone, ist länger als die Mindestzeit (Standard: mehr als 8 Stunden) unterwegs und kommt zurück,
fragt sie auf dem Handy nach Reiseziel, Zweck, Kilometern (und ggf. Übernachtung/Mahlzeiten) und erzeugt die PDF.

## Installation
1. Ordner `custom_components/reisekosten` nach `<config>/custom_components/` kopieren und Home Assistant neu starten.
2. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Reisekosten**.
3. Pauschalen, Kürzungen, km-Sätze und Konten unter *Konfigurieren* anpassen (Standard: Deutschland 2026).

PDFs liegen standardmäßig unter `<config>/www/reisekosten/` (abrufbar über `/local/reisekosten/<datei>`).
In den Optionen kann ein anderer **Speicherort** gewählt werden (z. B. `/media/reisekosten` oder `/share/Reisekosten`). Der Speicherort ist in den Optionen ein Dropdown (Standard, `/media`, `/share`, deren Unterordner, erlaubte Ordner) – eigene Pfade lassen sich eintippen.
Optional wird die PDF zusätzlich in den App-Ordner der Home-Assistant-OneDrive-Integration (Unterordner `Reisekosten`) hochgeladen; das nutzt die vorhandene OneDrive-Anmeldung.
Nur Ordner unterhalb von `www` bekommen einen Link in der Benachrichtigung, sonst wird der Pfad angezeigt.

## Kalender
In den Grunddaten können ein oder mehrere Kalender gewählt werden. Nach einer Reise sucht die Integration den Termin mit der größten Überschneidung und schlägt Ziel (Ort, sonst Titel) und Zweck (Titel) vor; auf dem Handy genügt ein Tipp auf „Übernehmen“.

## Einstellungen
Optionen → *Grunddaten* (Person, Zone, Handy, Name/Firma/Adresse, Kalender, Speicherort, OneDrive) und *Rechtliche Vorgaben und Konten*. Ein Gerätewechsel ist dort ohne Neueinrichtung möglich.

## Entitäten fürs Dashboard
Die Integration legt ein Gerät „Reisekosten“ mit diesen Entitäten an (die IDs hängen von der Sprache ab, hier die deutschen):

| Entität | Inhalt |
|---|---|
| `binary_sensor.reisekosten_unterwegs` | An, solange die Person außerhalb der Zone ist (Attribut `seit`) |
| `sensor.reisekosten_letzte_abrechnung` | Nummer der letzten Abrechnung; Attribute `betrag`, `reise`, `zweck`, `von`, `bis`, `datei`, `link` |
| `sensor.reisekosten_summe_monat` | Summe der Abrechnungen im laufenden Monat (EUR) |
| `sensor.reisekosten_summe_jahr` | Summe im laufenden Jahr (EUR) |
| `sensor.reisekosten_reisen_dieses_jahr` | Anzahl der Abrechnungen im laufenden Jahr |
| `sensor.reisekosten_offene_reisen` | Anzahl unbeantworteter Reisen; Attribut `reisen` mit Start, Ende und der offenen Frage |

Beispielkarte:

```yaml
type: entities
title: Reisekosten
entities:
  - binary_sensor.reisekosten_unterwegs
  - sensor.reisekosten_letzte_abrechnung
  - sensor.reisekosten_summe_monat
  - sensor.reisekosten_summe_jahr
  - sensor.reisekosten_reisen_dieses_jahr
  - sensor.reisekosten_offene_reisen
```

Link zur letzten PDF (nur bei Ablage unter `www`):

```yaml
type: markdown
content: >
  [Letzte Abrechnung öffnen]({{ state_attr('sensor.reisekosten_letzte_abrechnung', 'link') }})
```

### Korrekturkarte
Zum Korrigieren gibt es zusätzlich Eingabe-Entitäten: `select.reisekosten_abrechnung` (Auswahl, neueste zuerst), `text.reisekosten_reise`, `text.reisekosten_zweck`, `text.reisekosten_gestellte_mahlzeiten`, `number.reisekosten_kilometer`, `switch.reisekosten_ubernachtung` sowie die Knöpfe „Abrechnung neu erzeugen“, „Abrechnung löschen“, „Offene Reise verwerfen“ und „Offene Frage erneut senden“. Mit `text.reisekosten_antwort_auf_offene_frage` lässt sich die Handy-Frage auch am Dashboard beantworten. Beim Auswählen werden die Felder mit den Werten der Abrechnung gefüllt; geändert wird erst nach „Abrechnung neu erzeugen“. (Abrechnungen vor 0.6.0 lassen sich nicht neu erzeugen.)

```yaml
type: entities
title: Abrechnung korrigieren
entities:
  - select.reisekosten_abrechnung
  - text.reisekosten_reise
  - text.reisekosten_zweck
  - text.reisekosten_gestellte_mahlzeiten
  - number.reisekosten_kilometer
  - switch.reisekosten_ubernachtung
  - entity: button.reisekosten_abrechnung_neu_erzeugen
    tap_action:
      action: toggle
  - entity: button.reisekosten_abrechnung_loschen
    tap_action:
      action: toggle
      confirmation:
        text: Abrechnung wirklich löschen?
  - type: section
    label: Offene Reise
  - text.reisekosten_antwort_auf_offene_frage
  - button.reisekosten_offene_reise_verwerfen
  - button.reisekosten_offene_frage_erneut_senden
```

(Die Kilometer-Zeile ist nur sinnvoll, wenn die Kilometer-Abrechnung eingeschaltet ist.)

## Dienste
- `reisekosten.add_trip` – Reise manuell anlegen (`start`, `end`; nicht angegebene Felder werden per Handy-Rückfrage erfragt)
- `reisekosten.answer` – Rückfrage ohne Handy beantworten
- `reisekosten.discard` – offene Reise verwerfen (keine Dienstreise)
- `reisekosten.regenerate` – Abrechnung mit gleicher Nummer neu erzeugen, optional mit korrigierten Angaben
- `reisekosten.delete_trip` – Abrechnung samt PDF (und OneDrive-Kopie) löschen
- `reisekosten.list_trips` – erstellte Abrechnungen auflisten

## Änderungen
Siehe [CHANGELOG.md](CHANGELOG.md).

## Hinweise
- Keine Steuerberatung. Pauschalen und Konten bitte mit dem Steuerberater abstimmen.
- Nicht umgesetzt: Dreimonatsfrist, Ausland, Belege/tatsächliche Übernachtungskosten, zweite Zone (Betriebsstätte).

## Haftungsausschluss
Diese Software wird unentgeltlich und **„wie besehen“ ohne jede Gewähr** bereitgestellt.

- **Keine Steuer- oder Rechtsberatung:** Die Berechnung von Pauschalen, Kürzungen, Mitternachtsregel, Kilometersätzen und Konten ist eine Hilfestellung. Für Richtigkeit, Vollständigkeit und Aktualität der Beträge und Vorgaben wird keine Gewähr übernommen. Steuerliche Regeln ändern sich und hängen vom Einzelfall ab.
- **Eigene Prüfung:** Jede erzeugte Abrechnung ist vor der Verwendung (Buchhaltung, Steuererklärung, Erstattung) selbst zu prüfen und bei Bedarf mit Steuerberater oder Finanzamt abzustimmen.
- **Haftung:** Die Nutzung erfolgt auf eigenes Risiko. Der Autor haftet – soweit gesetzlich zulässig – nicht für Schäden, die aus der Nutzung oder Nichtverfügbarkeit der Software entstehen, etwa fehlerhafte Abrechnungen, nicht erstellte oder verlorene PDFs, Steuernachzahlungen oder Datenverlust. Unberührt bleibt die Haftung für Vorsatz und grobe Fahrlässigkeit, für die Verletzung von Leben, Körper und Gesundheit sowie eine nach zwingendem Recht bestehende Haftung.
- **Datenschutz:** Die Integration verarbeitet Standort-Status der gewählten Person, Kalendertermine und Reisedaten ausschließlich in deiner Home-Assistant-Installation. Nur wenn du den OneDrive-Upload aktivierst, wird die fertige PDF an OneDrive übertragen.
- Kein Zusammenhang mit Onexma oder anderen Anbietern von Reisekostenabrechnungen; Namen sind Marken ihrer jeweiligen Inhaber.

## Entwicklung
`python3 -m unittest discover -s tests` · `python3 demo.py` erzeugt eine Beispiel-PDF.
