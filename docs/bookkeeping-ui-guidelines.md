# Bookkeeping UI-Richtlinien

Diese Datei ist die verbindliche UI-Referenz für den Bookkeeping-Bereich von Quintus. Sie beschreibt die bereits etablierte Oberfläche und ist bei künftigen Änderungen beizubehalten. Fachliche Regeln und Systemabläufe stehen weiterhin in `docs/bookkeeping-system.md`.

Die Richtlinie wird nur erweitert, wenn eine neue Konvention allgemein für mehrere Bookkeeping-Seiten relevant ist. Einmalige Seitendetails gehören in das jeweilige Template und nicht in diese Datei.

## Leitbild

Die Bookkeeping-Oberfläche ist eine kompakte, sachliche Arbeitsoberfläche für wiederkehrende Buchhaltungsaufgaben. Sie priorisiert schnelle Orientierung, klar erkennbare Primäraktionen, gut scannbare Tabellen und verlässliches Formularverhalten. Bestehende Begriffe, Farben und Interaktionsmuster werden wiederverwendet; Änderungen sollen wie eine Fortsetzung der vorhandenen Oberfläche wirken, nicht wie ein Redesign.

Alle sichtbaren Texte sind auf Deutsch. Fachliche Logik, Statusübergänge und Berechtigungen dürfen durch reine UI-Arbeiten nicht verändert werden.

## Referenzimplementierungen

- `bookkeeping/templates/bookkeeping/base.html`: Seitenrahmen, Navigation, globales Verhalten für Zeitraumfilter
- `bookkeeping/templates/bookkeeping/overview.html`: Dashboard, Kennzahlen, Filter, Exportleiste und Transaktionstabellen
- `bookkeeping/templates/bookkeeping/manual_invoice_list.html`: Uploadbereich und kompakte Listenansicht
- `bookkeeping/templates/bookkeeping/manual_invoice_edit.html`: Statusleiste, Datenformular, Buchungszeilen und Aktionshierarchie
- `bookkeeping/templates/bookkeeping/booking_entry.html`: kompakte Quelldaten, Belege, editierbare Buchungstabelle und Formularabschluss
- `bookkeeping/templates/bookkeeping/_booking_entry_form_row.html`: Felder, Nur-Lese-Werte und Fehlermeldungen innerhalb einer Buchungszeile
- `bookkeeping/templates/bookkeeping/_matching_rule_table.html`: dichte Verwaltungstabelle mit Icon-Aktionen und Statusdarstellung
- `bookkeeping/templates/bookkeeping/*confirm*.html` und `matching_rule_delete.html`: Bestätigungsseiten für destruktive Aktionen
- `bookkeeping/static/bookkeeping/css/bookkeeping.css`: zentrale Gestaltung aller Bookkeeping-Komponenten

## Seitenaufbau

### Standard

- Jede Seite verwendet `bookkeeping/base.html` und bleibt innerhalb von `.bookkeeping-main`.
- Der Inhaltsbereich beginnt mit einer semantischen Section und einer `.bookkeeping-page-heading`.
- Der Inhaltsbereich besitzt genau ein `h1.bookkeeping-page-title`. Eine kurze Einordnung steht direkt darunter als `.bookkeeping-page-description`; die globale Kopfzeile aus `base.html` bleibt davon unberührt.
- Fachliche Teilbereiche verwenden `h2.bookkeeping-section-title` oder bei kleineren Unterabschnitten `h2.bookkeeping-subsection-title`.
- Zusammengehörige Inhalte liegen in flachen `.bookkeeping-card`-Blöcken. Karten werden nicht für jeden einzelnen Wert oder jedes einzelne Feld verschachtelt.
- Seitennachrichten stehen nach der Überschrift in `.bookkeeping-message-stack` mit `aria-live="polite"`; einzelne Meldungen verwenden Bootstrap-Alerts und `role="alert"`.

Bevorzugtes Grundmuster:

```html
<section class="bookkeeping-rules-section" aria-labelledby="page-heading">
    <div class="bookkeeping-page-heading">
        <div>
            <h1 id="page-heading" class="bookkeeping-page-title">Seitentitel</h1>
            <p class="bookkeeping-page-description">Kurze Einordnung.</p>
        </div>
    </div>

    <section class="bookkeeping-card" aria-labelledby="section-heading">
        <div class="bookkeeping-card-heading">
            <h2 id="section-heading" class="bookkeeping-section-title">Abschnitt</h2>
        </div>
    </section>
</section>
```

### Gewünschtes Verhalten

- Die wichtigsten Informationen und Aktionen sind ohne unnötiges Scrollen sichtbar.
- Abstände bleiben kompakt und folgen den vorhandenen Klassen; neue lokale Abstandsvarianten sind zu vermeiden.
- Auf schmalen Ansichten stapeln sich Überschriften, Filter und Formulare. Tabellen bleiben horizontal scrollbar.

### Anti-Patterns

- Kein zweites inhaltliches `h1` für Unterabschnitte einer Seite.
- Keine großen Hero-Bereiche, dekorativen Leerflächen oder stark gerundeten Karten.
- Keine tief verschachtelten Karten und keine neue visuelle Designsprache für eine einzelne Seite.
- Keine statischen Inline-Styles im Template. Dynamische Einzelwerte wie eine berechnete Fortschrittsbreite bleiben die begründete Ausnahme.

## Tabellen

### Standard

- Lesetabellen verwenden `.bookkeeping-table-wrap` und `.bookkeeping-data-table` sowie eine fachliche Tabellenklasse, zum Beispiel `.bookkeeping-transaction-table` oder `.bookkeeping-rules-table`.
- Scrollbare Tabellenbereiche erhalten `role="region"`, einen beschreibenden `aria-label` und `tabindex="0"`.
- Spaltenüberschriften verwenden `scope="col"`. Die Aktionsspalte steht links und heißt „Aktionen“.
- Beträge stehen rechtsbündig über `.bookkeeping-amount`; Datum, Richtung und Status bleiben kompakt und nicht umbrechend. Längere Namen, Zwecke und Details dürfen umbrechen.
- Die vorhandenen dezenten Zeilenlinien, weißen Datenzeilen, Hover-Zustände und fixierten Tabellenköpfe werden über `.bookkeeping-data-table` beibehalten. Zebra-Striping und vertikale Zellrahmen werden nicht verwendet.
- Seltene oder umfangreiche Zusatzinformationen werden mit nativem `<details>` in der betroffenen Zelle angeboten, wie in `overview.html` und `_matching_rule_table.html`.
- Fehlen Datensätze, erscheint eine kurze `.bookkeeping-empty-state` statt einer leeren Tabelle.

### Editierbare Buchungszeilen

- Buchungsformsets verwenden `.bookkeeping-entry-table-wrap` und `.bookkeeping-entry-table`.
- Editierbare Felder wirken im Ruhezustand tabellenartig. Hover und Fokus machen die Bearbeitbarkeit sichtbar; fehlerhafte Felder erhalten `.is-invalid`.
- Abgeleitete, nicht editierbare Werte werden als `.bookkeeping-entry-readonly-value` dargestellt. Falls sie für den POST benötigt werden, wird zusätzlich ein Hidden Field übertragen; es wird kein scheinbar editierbares Textfeld gezeigt.
- Jede Tabellenzelle besitzt entweder eine sichtbare Beschriftung durch den Tabellenkopf oder ein `label.visually-hidden` für das konkrete Feld.
- Das Django-Management-Formular bleibt erhalten. Beim Entfernen einer bestehenden Zeile wird das `DELETE`-Feld gesetzt und die Zeile ausgeblendet; neue Zeilen werden aus einem `<template>` ergänzt.

### Anti-Patterns

- Keine Umwandlung dichter Arbeitstabellen in Kartenlisten auf kleinen Bildschirmen.
- Keine abgeschnittenen Werte ohne zugängliche Möglichkeit, den vollständigen Inhalt zu lesen.
- Keine Textbuttons in jeder Tabellenzeile, wenn die etablierten Icon-Aktionen denselben Zweck kompakter erfüllen.
- Keine kritischen Informationen ausschließlich in einem standardmäßig geschlossenen `<details>`.

## Aktionen

### Seiten- und Formularaktionen

- Die primäre Abschlussaktion steht zuerst als `.btn-primary`, zum Beispiel „Prüfen und abschließen“.
- Speichern, Hinzufügen oder Bearbeiten verwendet in der Regel `.btn-outline-primary`.
- Abbrechen, Zurücknavigation und technische Wiederholungen verwenden `.btn-outline-secondary`.
- Zurücksetzen verwendet `.btn-outline-warning` oder in kompakten Zeilenaktionen eine neutrale sekundäre Darstellung.
- Destruktive Aktionen verwenden in dichten Listen in der Regel `.btn-outline-danger`. `.btn-danger` ist bewusst hervorgehobenen Löschoptionen und der endgültigen Bestätigung vorbehalten.
- Formularaktionen werden einmalig in `.bookkeeping-entry-form-actions`, `.bookkeeping-note-form-actions` oder `.bookkeeping-confirmation-actions` zusammengefasst. „Abbrechen“ erscheint pro Bearbeitungsseite nur einmal.
- Gleichrangige Exporte dürfen gemeinsam primär dargestellt werden. Sonst soll es pro Aktionsgruppe nur eine klar führende Aktion geben.

Referenz für Bearbeitungsseiten:

```html
<div class="bookkeeping-entry-form-actions">
    <button type="submit" name="action" value="finalize" class="btn btn-primary">Prüfen und abschließen</button>
    <button type="submit" name="action" value="save_draft" class="btn btn-outline-primary">Entwurf speichern</button>
    <a href="..." class="btn btn-outline-secondary">Abbrechen</a>
</div>
```

### Tabellenaktionen

- Wiederkehrende Zeilenaktionen stehen in `.bookkeeping-action-buttons.bookkeeping-icon-action-group`.
- Jede Icon-Aktion verwendet `.bookkeeping-icon-action`, ein Bootstrap Icon mit `aria-hidden="true"`, ein aussagekräftiges `title`, ein `aria-label` und einen `.visually-hidden`-Text.
- Links werden für Navigation und GET-Ziele verwendet. Zustandsändernde POST-Aktionen bleiben Buttons in kleinen, eigenständigen Formularen mit CSRF-Schutz.
- Externe Paperless-Links öffnen mit `target="_blank"` und `rel="noopener noreferrer"`.

### Seltene und destruktive Aktionen

- Seltene Aktionen dürfen unter einem verständlich beschrifteten nativen `<details>` wie „Weitere Aktionen“ progressiv offengelegt werden.
- Zurücksetzen und Löschen führen auf eine eigene Bestätigungsseite. Die Bestätigung erklärt konkret, was in Quintus und Paperless erhalten bleibt oder gelöscht wird.
- Eine destruktive Aktion wird nicht gleichzeitig in der Hauptaktionsleiste und in einem zweiten Bereich angeboten.

### Anti-Patterns

- Keine unbeschrifteten Icon-Buttons.
- Keine verschachtelten Formulare.
- Keine zustandsändernden Aktionen als ungeschützte GET-Requests.
- Keine Browser-`confirm()`-Dialoge, wenn bereits eine fachlich erklärende Bestätigungsseite existiert.
- Keine Duplikate von Speichern, Abbrechen, Zurücksetzen oder Löschen auf derselben Bearbeitungsseite.

## Formulare und Validierung

### Standard

- Widgets erhalten in `bookkeeping/forms.py` zentral `.form-control`, `.form-select` oder `.form-check-input`.
- Sichtbare Einzelfelder besitzen ein korrekt verknüpftes `.form-label`. Tabellenfelder verwenden bei Bedarf `label.visually-hidden`.
- Datumsfelder zeigen das österreichische Format `TT.MM.JJJJ`; Dezimalfelder unterstützen Dezimalkomma und verwenden `inputmode="decimal"`.
- Breite Formulare werden in vorhandenen Grids gruppiert. Fachlich zusammengehörige Felder bleiben in derselben Karte.
- Uploads verwenden ein eigenes Formular mit `multipart/form-data`, Dateityp-Einschränkung und einer direkt zugeordneten Uploadaktion.
- Die serverseitige Validierung bleibt maßgeblich. Clientseitige Summen oder Vorschauen sind nur unmittelbares Feedback und ersetzen keine Django-Validierung.

### Fehlerdarstellung

- Eine zusammenfassende `.bookkeeping-validation-alert` steht vor dem betroffenen Formularbereich.
- Feldfehler stehen unmittelbar unter dem Feld als `.bookkeeping-formset-error`, `.bookkeeping-entry-cell-errors` oder sichtbares `.invalid-feedback`.
- Fehlerhafte Widgets erhalten `.is-invalid` und `aria-invalid="true"` über das bestehende Bound-Field-Verhalten.
- Gebundene Benutzereingaben bleiben nach einem Validierungsfehler sichtbar. Fehlermeldungen dürfen nicht durch dynamisches Ergänzen oder Entfernen von Formset-Zeilen verloren gehen.

### Anti-Patterns

- Keine Platzhalter als Ersatz für Labels.
- Keine rein clientseitige fachliche Validierung.
- Keine deaktivierten oder schreibgeschützten Eingaben, die optisch wie normale editierbare Felder wirken.
- Keine neuen JavaScript-Komponenten für Verhalten, das mit Django, Bootstrap oder nativen HTML-Elementen verständlich lösbar ist.

## Status, Richtung und Beträge

- Richtung wird mit `.bookkeeping-badge-incoming` beziehungsweise `.bookkeeping-badge-outgoing` dargestellt.
- Allgemeine Zustände verwenden `.bookkeeping-badge-status`, `.bookkeeping-badge-active`, `.bookkeeping-badge-inactive` oder `.bookkeeping-badge-type`.
- Prozesszustände verwenden `.bookkeeping-status-badge` mit den Varianten `success`, `info`, `warning` und `danger`.
- Positive und negative Beträge verwenden `.bookkeeping-amount-positive` beziehungsweise `.bookkeeping-amount-negative`; Beträge bleiben rechtsbündig und nicht umbrechend.
- Farbe unterstützt die Bedeutung, ersetzt aber nie den sichtbaren Statustext. „Abgelegt“, „Übertragung läuft“ oder „Fehler“ müssen weiterhin lesbar im Badge stehen.
- Fehlermeldungen zu einem Status stehen direkt daneben oder darunter als `.bookkeeping-status-error` beziehungsweise `.bookkeeping-table-detail`.

Neue Statusfarben werden nicht lokal im Template eingeführt. Zuerst ist zu prüfen, ob eine vorhandene semantische Variante passt.

## Typografie und Dichte

- `.bookkeeping-page-title` ist die größte inhaltliche Überschrift. Abschnitts- und Unterabschnittstitel bleiben sichtbar kleiner.
- Beschreibungen, Labels, Tabellenhilfen und Metadaten verwenden die vorhandenen gedämpften Farben und kleineren Schriftgrößen.
- Beträge, Summen und zentrale Kennzahlen dürfen durch Gewicht und semantische Farbe hervorgehoben werden; zusätzliche große Schriftstufen sind nicht erforderlich.
- Die Oberfläche bleibt kompakt: Standardfelder sind ungefähr `2.25rem` hoch, Tabellenzellen haben enge Abstände, und Aktions-Icons besitzen ein einheitliches quadratisches Ziel von `2rem`.

## Zeitraumsteuerung und unmittelbares Feedback

- Monats- und Quartalsumschalter sind serverseitige Submit-Buttons und zeigen den aktiven Zustand mit `.btn-primary`.
- Zeitraum-Selects liegen in Formularen mit `data-bookkeeping-period-form`. Das globale Skript in `base.html` sendet das Formular bei einer Select-Änderung automatisch ab; ein zusätzlicher Button „Anzeigen“ wird nicht benötigt.
- Erforderliche Kontextparameter wie Status oder Zeitraumtyp werden als Hidden Fields erhalten.
- Dynamische Formset-Zeilen und Summenfeedback werden mit kleinem, lokalem JavaScript im betreffenden Template umgesetzt. Das Verhalten muss ohne Änderung der serverseitigen Validierung auskommen.
- Statusmeldungen und dynamische Summen verwenden bei Bedarf `aria-live="polite"`; Validierungsfehler verwenden `role="alert"`, nicht nur Farbe.

## Responsive Verhalten und Barrierefreiheit

- Der vorhandene Desktop-Arbeitsbereich bleibt die Primäransicht. Unter den bestehenden Breakpoints stapeln sich Grids, Filter und Aktionsbereiche sinnvoll.
- Breite Tabellen scrollen horizontal innerhalb ihres Wrappers; der gesamte Seitenrahmen darf nicht unnötig horizontal überlaufen.
- Interaktive Elemente behalten den zentral definierten sichtbaren `:focus-visible`-Zustand.
- Sections und Karten mit Überschriften verwenden `aria-labelledby`. Reine Icon-Aktionen benötigen immer einen zugänglichen Namen.
- Native HTML-Elemente wie `<button>`, `<details>`, `<summary>`, `<table>`, `<dl>` und korrekt verknüpfte `<label>` werden bevorzugt.
- Der Fokus wird nach dem Laden nicht automatisch versetzt. Es gibt keine unerwarteten Dialoge oder automatische Navigation außerhalb der ausdrücklich gewählten Filteränderung.

## Pflege- und Prüfcheckliste

Vor Abschluss einer Bookkeeping-UI-Änderung ist zu prüfen:

1. Nutzt die Seite vorhandene Klassen und eine der oben genannten Referenzseiten als Muster?
2. Sind Seitentitel, Abschnitte, Karten und Abstände hierarchisch eindeutig und kompakt?
3. Gibt es pro Bereich eine klare Primäraktion und keine doppelten Aktionen?
4. Sind Tabellen scrollfähig, semantisch beschriftet und für Beträge, Status sowie lange Inhalte passend ausgerichtet?
5. Besitzen alle Felder Labels, sichtbare Fokuszustände und unmittelbare Fehlermeldungen?
6. Bleiben POST-Aktionen CSRF-geschützt und destruktive Vorgänge bestätigt?
7. Funktioniert die Seite bei schmaler Breite ohne abgeschnittene Pflichtinformationen?
8. Wurden bestehende Template-Tests für relevante DOM-Verträge angepasst oder ergänzt, zum Beispiel Aktionsreihenfolge, genau ein „Abbrechen“, zugängliche Icon-Aktionen oder automatisches Absenden von Zeitraumfiltern?
9. Wurden Fachlogik, Modelle, Daten und Statusübergänge unverändert gelassen, sofern sie nicht ausdrücklich Teil des Auftrags waren?

Die Richtlinie selbst wird nur angepasst, wenn aus einer Änderung eine dauerhaft wiederverwendbare Konvention für den gesamten Bookkeeping-Bereich entsteht.
