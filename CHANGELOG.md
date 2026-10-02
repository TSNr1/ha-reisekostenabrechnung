# Changelog

Alle wichtigen Änderungen an dieser Integration. Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [0.12.0]
### Verbessert
- **Rechtliche Vorgaben übersichtlicher:** In den Einstellungen gelten standardmäßig die hinterlegten gesetzlichen Sätze des Reisejahres. Die Eingabefelder für Pauschalen, Kürzungen, km-Sätze und Mitternachtsregel erscheinen erst im nächsten Schritt, wenn du den Schalter **„Eigene Werte statt der gesetzlichen Sätze verwenden“** aktivierst. Konten, Zahlweise und „Kilometer abrechnen“ bleiben direkt im ersten Schritt.
### Hinweise
- Bestehende Einstellungen bleiben erhalten: Wer eigene Werte eingetragen hat, sieht den Schalter aktiv; wer nur die Standardwerte hatte, nutzt jetzt automatisch die Jahrestabelle. Eigene Werte gelten weiter für alle Jahre. Nach dem Update Home Assistant neu starten.

## [0.11.0]
### Neu
- **Sätze pro Jahr.** Die Inlandspauschalen und alle übrigen Regeln sind jetzt je Jahr hinterlegt. Eine Reise wird mit den Sätzen ihres Reisejahres berechnet, auch wenn sie erst im Folgejahr abgerechnet wird. Ändert der Gesetzgeber die Sätze, kommt mit einem Update ein Eintrag für das neue Jahr dazu; frühere Abrechnungen bleiben unverändert. Ein Jahr ohne eigenen Eintrag nutzt die Sätze des Vorjahres.
### Verbessert
- In den Einstellungen werden nur noch deine **eigenen Abweichungen** gespeichert. Bisher wurde bei jedem Speichern eine Kopie aller Werte abgelegt, die künftige Sätze überschrieben hätte. Alte Kopien werden automatisch wie Standardwerte behandelt.
### Hinweise
- Für 2024 bis 2026 gelten unverändert 14 € / 28 € / 14 €. Die Auslandspauschalen sind weiterhin nicht enthalten.
- Wer in den Einstellungen bewusst andere Werte eingetragen hat, behält sie für alle Jahre. Nach dem Update Home Assistant neu starten.

## [0.10.1]
### Behoben
- **Tippen auf die Benachrichtigung „Abrechnung erstellt“ öffnete in der Android-App nur „401: Unauthorized“.** Die App hängt an relative Links eigene Parameter an, wodurch der signierte Link ungültig wurde. Der Link in der Benachrichtigung ist jetzt eine vollständige Adresse (externe URL bevorzugt, sonst interne) und öffnet das PDF im Browser.
### Hinweise
- In Home Assistant sollte unter Einstellungen → System → Netzwerk eine externe oder interne URL eingetragen sein. Das Sensor-Attribut `link` bleibt ein relativer Pfad.
- Nach dem Update Home Assistant neu starten.

## [0.10.0]
### Behoben (Datenschutz)
- **PDFs sind nicht mehr öffentlich abrufbar.** Bisher lagen sie standardmäßig in `www/reisekosten` und waren damit ohne Anmeldung unter `/local/…` erreichbar. Der neue Standardordner ist `<config>/reisekosten`. Die PDFs werden nur noch über Home Assistant ausgeliefert, mit Anmeldung oder über einen signierten, befristeten Link (Handy-Benachrichtigung 7 Tage, Sensor-Attribut `link` 24 Stunden, stündlich erneuert).
### Hinweise
- Neue Abrechnungen landen im neuen Ordner, bestehende PDFs bleiben, wo sie sind, und sind weiter abrufbar. **Lösche alte PDFs unter `www/reisekosten`**, falls vorhanden, und wähle keinen Speicherort unterhalb von `www`.
- Nach dem Update Home Assistant neu starten. Wer eigene Links auf `/local/reisekosten/…` gebaut hat, nutzt jetzt das Sensor-Attribut `link`.

## [0.9.0]
### Neu
- **Tätigkeit:** In den Grunddaten wählst du Selbstständig, Angestellt oder Beides. Bei „Beides“ fragt die Integration bei jeder Reise auf dem Handy zuerst, welche Tätigkeit es war (Knöpfe „Selbstständig“, „Angestellt“, „Keine Dienstreise“).
- **Kontenrahmen SKR03/SKR04:** Die Konten der Buchungsliste (Verpflegungsmehraufwand, Fahrtkosten) werden nach Kontenrahmen und Tätigkeit automatisch gesetzt. Wer eigene Konten nutzt, wählt „Eigene Konten“ – bestehende Einstellungen bleiben dabei erhalten.
- **Arbeitsstätte (Zone):** Wege zwischen Wohnung und Arbeitsstätte gelten nicht als Dienstreise und fließen nicht in die Tagessumme ein. Dienstreisen beginnen und enden an Wohnung oder Arbeitsstätte.
- **Kilometer-Vorschlag:** Mit einem Kilometerzähler-Sensor schlägt die Integration die gefahrenen Kilometer (Differenz zwischen Abfahrt und Ankunft) bei der Kilometer-Frage vor; ein Tipp übernimmt sie.
### Hinweise
- Selbstständige ohne Arbeitszone merken keinen Unterschied: Es gelten die bisherigen Abläufe.
- Neue Felder in den Grunddaten: Tätigkeit, Arbeitsstätte, Kontenrahmen, Kilometerzähler. Nach dem Update Home Assistant neu starten.
- Bestehende Installationen behalten ihre eigenen Konten (Kontenrahmen „Eigene Konten“); neu eingerichtet startet die Integration mit SKR04.

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
