# Changelog

Alle wichtigen Änderungen an dieser Integration. Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [0.8.3]
### Neu
- **Knopf „Keine“** bei der Frage nach gestellten Mahlzeiten (und nach Kilometern, falls aktiviert) – kein „-“ mehr eintippen.
### Behoben
- Beim Anreisetag steht jetzt die volle Zeit bis Mitternacht („18:00 Std.“ statt „17:59 Std.“). Die Beträge ändern sich nicht.

## [0.8.2]
### Verbessert
- **Mehrere Kalendertermine pro Reise:** Überschneiden sich mehrere Termine mit der Abwesenheit (z. B. vier Termine an zwei Orten in zwei Wochen), werden sie nach Beginn sortiert zusammengefasst. Bei Adressen mit Postleitzahl wird nur der Ort übernommen, doppelte Einträge erscheinen nur einmal. Beispiel: Ziel „Sinsheim, Fellbach“, Zweck „Inhouse Reha-Med Sinsheim; VPT KGG Fellbach; TRENA Fellbach“.
- Kurze Termine (unter 2 Stunden Überschneidung, z. B. ein Telefonat) werden ignoriert, sobald es einen längeren Termin gibt.

## [0.8.1]
### Behoben
- Die neuen Dashboard-Entitäten aus 0.8.0 hatten keine Namen (alle hießen wie das Gerät, z. B. „Reisekosten Martin“, mit Entity-IDs wie `text.…_2`). Die Übersetzungen waren falsch aufgebaut und sind korrigiert.
### Hinweise
- Bereits angelegte Entitäten behalten ihre alte Entity-ID und müssen einmalig umbenannt werden (Einstellungen → Entitäten); die Anzeigenamen werden nach Neustart von selbst richtig.

## [0.8.0]
### Neu
- **Korrekturkarte fürs Dashboard:** Neue Eingabe-Entitäten, mit denen Abrechnungen direkt am Dashboard korrigiert werden können: Auswahl der Abrechnung, Felder für Reise, Zweck, Mahlzeiten, Kilometer und Übernachtung, dazu Knöpfe „Abrechnung neu erzeugen“ und „Abrechnung löschen“.
- **Offene Fragen am Dashboard:** Feld „Antwort auf offene Frage“, Knöpfe „Offene Reise verwerfen“ und „Offene Frage erneut senden“.
- Fertige Beispielkarte im README.
### Hinweise
- Nach dem Update Home Assistant neu starten, damit die neuen Entitäten angelegt werden. Abrechnungen vor 0.6.0 lassen sich weiterhin nicht neu erzeugen.

## [0.7.0]
### Neu
- **Entitäten fürs Dashboard:** Neues Gerät „Reisekosten“ mit „Unterwegs“ (an/aus), „Letzte Abrechnung“ (mit Betrag, Zeitraum und Link zur PDF), „Summe Monat“, „Summe Jahr“, „Reisen dieses Jahr“ und „Offene Reisen“. Beispielkarten stehen im README.

## [0.6.1]
### Neu
- **Haftungsausschluss** im README (keine Gewähr, keine Steuerberatung, eigene Prüfung, Datenschutzhinweis) und als Hinweis im Einrichtungsdialog.

## [0.6.0]
### Neu
- **„Keine Dienstreise“:** Bei der ersten Handy-Frage gibt es einen Knopf, mit dem sich private Ausflüge verwerfen lassen (auch als Dienst `reisekosten.discard`).
- **Nur bei passendem Kalendertermin nachfragen:** Neue Option in den Grunddaten; ohne Termin im gewählten Kalender bleibt die Integration still.
- **Mehrere Abwesenheiten am selben Tag werden zusammengerechnet:** Kurze Fahrten desselben Kalendertages zählen zusammen (steuerlich maßgeblich). Hinweis dazu steht auf der Abrechnung. Ist der Tag schon abgerechnet, bringt eine weitere Abwesenheit keine zweite Pauschale.
- **Korrigieren und löschen:** Dienste `reisekosten.regenerate` (PDF mit gleicher Nummer neu erzeugen, optional mit korrigierten Angaben), `reisekosten.delete_trip` (Abrechnung, PDF und OneDrive-Kopie löschen, Zähler wird angepasst) und `reisekosten.list_trips` (Übersicht der Nummern).
### Hinweise
- Abrechnungen, die vor 0.6.0 erstellt wurden, lassen sich löschen, aber nicht neu erzeugen.

## [0.5.1]
### Neu
- Icon und Logo für die Integration (erscheint in Home Assistant) und im README.

## [0.5.0]
### Neu
- **Kalender-Vorschläge:** In den Grunddaten lassen sich ein oder mehrere Kalender wählen. Nach einer Reise wird der Termin mit der größten Überschneidung gesucht; Ziel (Ort, sonst Titel) und Zweck (Titel) werden auf dem Handy vorgeschlagen, ein Tipp auf „Übernehmen“ genügt.
- **Optionen als Menü:** *Grunddaten* (zu überwachende Person, Zone, Handy für die Rückfragen, Name, Firma, Adresse, Kalender, Speicherort, OneDrive) und *Rechtliche Vorgaben und Konten*.
### Verbessert
- Gerätewechsel (anderes Handy) und Personenwechsel sind jetzt nachträglich ohne Neueinrichtung möglich.

## [0.4.0]
### Neu
- **Speicherort als Dropdown:** Standardordner, `/media`, `/share` und deren Unterordner sowie erlaubte Ordner; eigene Pfade bleiben möglich.
- **Optionaler OneDrive-Upload** in den App-Ordner der Home-Assistant-OneDrive-Integration (Unterordner „Reisekosten“), über die vorhandene Anmeldung.
### Behoben
- Fehlende deutsche und englische Bezeichnungen in den Optionen ergänzt.

## [0.3.0]
### Neu
- **Wählbarer Speicherort** für die PDFs; Ordner außerhalb von `www` zeigen den Pfad statt eines Links in der Benachrichtigung.
- Schalter **„Kilometer abrechnen“** (aus bei Betriebsfahrzeug: keine km-Frage, keine km-Zeile).
- `reisekosten.add_trip` fragt nicht angegebene Felder per Handy-Rückfrage nach.
### Hinweise
- Die Übernachtungspauschale wird nicht berechnet; tatsächliche Hotelkosten laufen über den Beleg in der Buchhaltung.

## [0.2.0]
### Neu
- Einrichtung über die Oberfläche, automatische Erkennung über eine `person`-Entität, Rückfragen auf dem Handy, PDF-Abrechnung (Aufstellung und Buchungsliste), fortlaufende Nummern, Dienste `add_trip` und `answer`.
- Rechtliche Vorgaben einstellbar: Pauschalen, Mindestzeit, Kürzungen, Kilometersätze, Mitternachtsregel, Konten.

[0.7.0]: https://github.com/TSNr1/ha-reisekostenabrechnung/releases/tag/v0.7.0
[0.6.1]: https://github.com/TSNr1/ha-reisekostenabrechnung/releases/tag/v0.6.1
[0.6.0]: https://github.com/TSNr1/ha-reisekostenabrechnung/releases/tag/v0.6.0
[0.5.1]: https://github.com/TSNr1/ha-reisekostenabrechnung/releases/tag/v0.5.1
[0.5.0]: https://github.com/TSNr1/ha-reisekostenabrechnung/releases/tag/v0.5.0
[0.4.0]: https://github.com/TSNr1/ha-reisekostenabrechnung/releases/tag/v0.4.0
