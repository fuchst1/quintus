# Aufbewahrungsrichtlinie für Dateien (Quintus)

## Ziel
Diese Richtlinie definiert, welche Dateien archiviert oder endgültig gelöscht werden dürfen.

## Statusmodell
- `aktiv`: Datei ist normal sichtbar und fachlich nutzbar.
- `archiviert`: Datei bleibt revisionssicher gespeichert, erscheint aber nicht mehr in Standardlisten.
- `endgültig gelöscht`: Datei und Binärinhalt wurden physisch entfernt (nur administrativer Sonderfall).

## Was darf archiviert werden
- Fehluploads, Dubletten und nicht mehr relevante Arbeitsdokumente.
- Verwaiste Dateien ohne aktive Zuordnung (`files_cleanup_orphans --archive`).
- Alte Zählerfotos, sofern ein neuer, dokumentierter Messstand vorhanden ist.

## Was nicht automatisch gelöscht werden darf
- Vertragsdokumente und Briefe mit rechtlicher Relevanz.
- Dateien mit möglicher Beweisfunktion (z. B. Zustandsfotos, Abrechnungsbelege).
- Alles, was noch einem aktiven Mietverhältnis/Liegenschaftsvorgang zugeordnet ist.

## Empfehlungen zur Frist
- Zählerfotos: mindestens bis zur nächsten vollständig plausibilisierten Jahresabrechnung.
- Allgemeine Dokumente/Briefe: mindestens 7 Jahre.
- Vertragsunterlagen: mindestens 10 Jahre nach Vertragsende.

## Technische Umsetzung in Quintus
- Standardaktion im UI ist **Archivieren** (Soft-Delete), kein physisches Löschen.
- Zugriff auf sensible Dateien erfolgt über geschützte Download-Views.
- Jeder Upload/Download/Archivierungsvorgang wird im Audit-Log (`DateiOperationLog`) protokolliert.
- Wiederholbare Wartungsjobs:
  - `files_audit`
  - `files_cleanup_orphans`
  - `files_generate_thumbnails`

## Endgültiges Löschen
- Nur durch Administratoren nach dokumentierter Prüfung.
- Vor physischem Löschen ist ein Audit-Durchlauf (`files_audit`) empfohlen.
