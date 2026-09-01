# Core Ledger – UI-Komponenten

Diese Datei beschreibt die wiederverwendbaren Bausteine der neuen Buchhaltungsoberfläche. `docs/DESIGN.md` bleibt die visuelle Quelle der Wahrheit. Die Referenz ist direkt unter `/bookkeeping/new-ui/components/` erreichbar und wird bewusst nicht in der normalen Navigation verlinkt.

Alle neuen Seiten erweitern `bookkeeping/new_ui/base.html`. Die kanonischen Werte stehen in `bookkeeping/static/bookkeeping/css/new_ui/tokens.css`; gemeinsame Darstellung und Zustände stehen in `components.css`. Seiten dürfen diese Regeln nicht mit eigenen Farben, Abständen oder Varianten überschreiben.

## Seitenkopf

**Zweck:** Ein gemeinsamer Einstieg mit Breadcrumbs, genau einer Seitenüberschrift, kurzer Beschreibung und optionalen Aktionen.

**Varianten:** Mit oder ohne Breadcrumbs, Beschreibung und Aktionen. `heading_level="2"` ist ausschließlich für eingebettete Referenzbeispiele vorgesehen; auf echten Seiten bleibt die Vorgabe leer und erzeugt `h1`.

**Eingaben:** `title` ist erforderlich. Optional sind `description`, `breadcrumbs` (Liste aus `label` und optional `url`) und `actions_template`. Der Aktions-Templatepfad muss serverseitig festgelegt werden und darf nie ungeprüft aus Request-Daten stammen.

**Regeln:** Normalerweise höchstens eine primäre Aktion; sie steht rechts. Breadcrumbs bilden eine echte Hierarchie ab. Beschreibung kurz halten.

**Nicht verwenden:** Für Abschnittsüberschriften, Status-Kacheln oder seitenindividuelle Kopfleisten.

```django
{% include "bookkeeping/new_ui/components/_page_header.html" with
    title="Manuelle Belege"
    description="Eingangsrechnungen prüfen und kontieren."
    breadcrumbs=breadcrumbs
    actions_template="bookkeeping/manual_invoices/_header_actions.html"
%}
```

## Schaltflächen

**Zweck:** Aktionen eindeutig priorisieren und in allen Zuständen konsistent darstellen.

**Varianten:** `.core-ledger-button--primary`, `--secondary`, `--quiet`, `--destructive`; `--icon` wird für reine Symbolschaltflächen mit einer dieser Varianten kombiniert. Default, Hover, Aktiv und Fokus entstehen nativ. `disabled` und `.is-loading` sind explizit. `.is-hovered`, `.is-focused` und `.is-active` dürfen außerhalb der Showcase-Seite nicht erzwungen werden.

**Eingaben:** Ein semantisches `button` oder `a`, ein konkretes deutsches Aktionslabel und optional ein dekoratives Bootstrap-Icon. Icon-only-Buttons benötigen `aria-label` und `title`.

**Regeln:** Pro Seite oder Dialog normalerweise nur eine primäre Aktion. Rot ausschließlich für destruktive Vorgänge; Abbrechen ist sekundär oder leise. Formulare mit längerem Submit erhalten `data-core-ledger-loading-form`, der Submit-Button `data-core-ledger-submit`; das Projektskript verhindert Doppelsubmits und erhält das Label.

**Nicht verwenden:** Als Statusanzeige, für nicht-interaktive Flächen oder mit vagen Labels wie „OK“.

```django
<button class="core-ledger-button core-ledger-button--primary" type="submit">
    <i class="bi bi-check-lg" aria-hidden="true"></i>
    <span>Buchung abschließen</span>
</button>
```

## Formulare und Nur-Lese-Werte

**Zweck:** Kompakte, zugängliche Dateneingabe mit klarer Korrekturhilfe.

**Varianten:** Normales Feld, Pflichtfeld, Feld mit Hilfe, ungültiges Feld und gruppierte Controls. Nur-Lese-Daten verwenden `.core-ledger-readonly` mit `dl`, `dt` und `dd`.

**Eingaben:** `.core-ledger-field` enthält eine sichtbare `.core-ledger-label` und `.core-ledger-control`. Hilfen verwenden `.core-ledger-help`; Fehler `.core-ledger-error`. `aria-describedby` verweist auf die jeweilige Hilfe beziehungsweise Fehlermeldung. Ungültige Controls erhalten `aria-invalid="true"` und `.is-invalid`.

**Regeln:** Placeholder ersetzen nie Labels. Ein sichtbarer Stern und der zusätzliche Screenreader-Text „(Pflichtfeld)“ markieren Pflichtangaben. Eine Validierungszusammenfassung verwendet `.core-ledger-validation-summary`, `role="alert"`, verlinkt jedes fehlerhafte Feld und die Meldung erklärt die Korrektur.

**Nicht verwenden:** Deaktivierte Inputs zur Anzeige unveränderlicher Werte oder Fehler, die nur farblich markiert sind.

```django
<div class="core-ledger-field">
    <label class="core-ledger-label" for="id_invoice_number">Rechnungsnummer</label>
    <input class="core-ledger-control is-invalid" id="id_invoice_number"
           name="invoice_number" aria-invalid="true"
           aria-describedby="invoice-number-error">
    <p class="core-ledger-error" id="invoice-number-error">
        Bitte die Rechnungsnummer vom Beleg eintragen.
    </p>
</div>
```

## Datentabellen

**Zweck:** Seitenabhängige Finanzdaten dicht, scannbar und zugänglich darstellen. Es gibt absichtlich kein generisches Tabellen-Partial.

**Varianten:** `.core-ledger-table` in `.core-ledger-table-wrap`; `.core-ledger-numeric`, `.core-ledger-date`, `.core-ledger-actions` und `.core-ledger-truncate`; Zeilen `.is-selected` und `.is-error`. Hover entsteht nativ, `.is-hovered` ist nur eine Showcase-Fixture.

**Eingaben:** Ein echtes `table` mit `caption`, `thead`, `tbody` und `scope` an Kopfzellen. Geld und Zahlen erhalten `core-ledger-numeric`; Datum wird mit `time datetime` ausgezeichnet. Sortierung steht als `aria-sort` am betreffenden `th`.

**Regeln:** Auswahl und Fehler immer zusätzlich mit Checkbox, Symbol oder Text kennzeichnen. Vollständiger gekürzter Text muss im DOM und für Tastatur beziehungsweise Hilfstechnologien erreichbar bleiben. Der letzte Bereich enthält sekundäre Zeilenaktionen. Auf kleinen Bildschirmen scrollt der Wrapper horizontal und ist per Tastatur fokussierbar, wenn Inhalt überläuft.

**Nicht verwenden:** Vollständige Zellgitter, einzelne Karten je Zeile oder ein Partial, das fachliche Spalten versteckt.

```django
<div class="core-ledger-table-wrap" tabindex="0" role="region" aria-label="Offene Buchungen">
    <table class="core-ledger-table">
        <caption>Offene Buchungen</caption>
        <thead><tr><th scope="col">Datum</th><th scope="col" class="core-ledger-numeric">Betrag</th></tr></thead>
        <tbody><tr><td><time datetime="2026-07-31">31.07.2026</time></td><td class="core-ledger-numeric">1.248,00 EUR</td></tr></tbody>
    </table>
</div>
```

Eine leere Tabellenzeile spannt alle Spalten und bindet darin `_empty_state.html` ein.

## Status-Badge

**Zweck:** Einen gespeicherten Modellstatus mit konsistenter Beschriftung, Semantik und Symbol anzeigen.

**Varianten:** `neutral`, `info`, `success`, `warning`, `error`. Diese Varianten sind Ergebnis der zentralen Registry und kein Template-Input.

**Eingaben:** Der Tag `{% status_badge family value %}` erwartet eine der Familien `bank_transaction`, `manual_invoice`, `manual_invoice_paperless`, `manual_invoice_ai`, `bank_statement_paperless` oder `supporting_document_transfer` sowie den gespeicherten Wert. Labels werden direkt aus den jeweiligen `TextChoices` abgeleitet. Unbekannte Familie oder unbekannter Wert ergibt neutral „Unbekannt“ mit Fragezeichen-Symbol.

**Regeln:** Immer `{% load bookkeeping_ui %}` verwenden und nie Variante, Farbe, Label oder Icon auf der Seite festlegen. Ein Badge ist nicht interaktiv und erhält keinen Hover- oder Pointer-Zustand. Text und Symbol transportieren die Bedeutung zusätzlich zur Farbe.

**Nicht verwenden:** Für Aktionen, freie Kategorien, Zähler oder dekorative Labels.

```django
{% load bookkeeping_ui %}
{% status_badge "bank_transaction" transaction.status %}
```

## Aktionsleiste

**Zweck:** Seitenaktionen in stabiler Reihenfolge am Ende eines Bearbeitungsablaufs gruppieren.

**Varianten:** `mode="standard"` oder `mode="sticky"` für ein langes Formular. Sticky nur einsetzen, wenn die Leiste keinen Inhalt oder Touch-Bedienelemente verdeckt.

**Eingaben:** Optional `feedback`, serverseitig kontrolliertes `actions_template` und `mode`. Das Actions-Partial enthält Zurück/Abbrechen, sekundäre Aktionen und ganz rechts höchstens eine primäre Aktion.

**Regeln:** Feedback bleibt mit `role="status"` nahe bei den blockierten Aktionen. Aktionsreihenfolge nicht pro Seite verändern.

**Nicht verwenden:** Als zweite Seitenkopfzeile, für globale Navigation oder auf reinen Leseseiten ohne Aktionen.

```django
{% include "bookkeeping/new_ui/components/_action_bar.html" with
    feedback=form_feedback
    actions_template="bookkeeping/booking/_actions.html"
    mode="sticky"
%}
```

## Meldung

**Zweck:** Handlungsrelevante Information, Erfolg, Warnung oder Fehler verständlich mitteilen.

**Varianten:** `info`, `success`, `warning`, `error`.

**Eingaben:** `variant` und `message` sind erforderlich; `title` ist optional. Inhalte sind Klartext und werden standardmäßig escaped.

**Regeln:** Meldungen nennen Ergebnis und gegebenenfalls den nächsten Schritt. Warnung und Fehler verwenden `role="alert"`; Information und Erfolg `role="status"`. Symbol und Text verhindern reine Farbcodierung.

**Nicht verwenden:** Als dekoratives Banner, dauerhafte Seitenbeschreibung oder Ersatz für eine feldnahe Validierung.

```django
{% include "bookkeeping/new_ui/components/_alert.html" with
    variant="error"
    title="Import fehlgeschlagen"
    message="Dateiformat prüfen und den Bankauszug erneut hochladen."
    only
%}
```

## Leerzustand

**Zweck:** Erklären, warum Daten fehlen und welche sinnvolle Folgeaktion verfügbar ist.

**Varianten:** Mit oder ohne Beschreibung, Symbol und Aktion; auch innerhalb einer leeren Tabellenzeile.

**Eingaben:** `empty_id` und `title` sind erforderlich. Optional: `description`, Bootstrap-Iconklasse `icon`, gemeinsam verwendete `action_url`, `action_label`, `action_icon` oder ein serverseitiges `action_template`. `action_template` und URL-Aktion nicht gleichzeitig setzen.

**Regeln:** Texte kurz und sachlich halten. Die Aktion zeigt den nächsten fachlichen Schritt, nicht beliebige Navigation.

**Nicht verwenden:** Während Daten laden, bei Fehlern oder als großflächige Illustration.

```django
{% include "bookkeeping/new_ui/components/_empty_state.html" with
    empty_id="empty-invoices"
    title="Keine Belege in diesem Zeitraum"
    description="Für Juli 2026 wurden noch keine Belege erfasst."
    icon="bi-receipt"
    action_url=create_url
    action_label="Beleg erfassen"
    only
%}
```

## Formulardialog

**Zweck:** Kurze Erfassungs- oder Bearbeitungsaufgaben im aktuellen Arbeitskontext erledigen.

**Varianten:** Mit oder ohne Beschreibung; nach ungültiger Serverantwort automatisch wieder geöffnet.

**Eingaben:** Erforderlich sind eine dokumentweit eindeutige `modal_id`, `title` und ein serverseitig kontrolliertes `body_template`. Optional sind `description`, `form_action`, `form_method` (Standard `post`), `cancel_label`, `submit_label` und `reopen_on_invalid`. Das Body-Partial enthält die fachlichen Formularfelder und gegebenenfalls die Validierungszusammenfassung.

**Regeln:** Der Bootstrap-Modalmechanismus übernimmt Fokusfalle, Escape, Backdrop und Rückgabefokus. Bei Serverfehlern `reopen_on_invalid=True` setzen; der Dialog bleibt so bei den sichtbaren Fehlern. Abbrechen steht vor der primären Aktion. Das gemeinsame Skript setzt den Loading-Zustand und verhindert Doppelsubmits.

**Nicht verwenden:** Für lange Formulare, mehrere abhängige Schritte, Dokumentvergleich oder Aufgaben, die viel Umgebungskontext benötigen; dafür eine eigene Seite verwenden.

```django
{% include "bookkeeping/new_ui/components/_form_modal.html" with
    modal_id="invoice-modal"
    title="Beleg erfassen"
    body_template="bookkeeping/invoices/_form_fields.html"
    form_action=create_url
    submit_label="Beleg speichern"
    reopen_on_invalid=form.errors
%}
```

## Karten und Bereiche

**Zweck:** Fachlich eigenständige Inhaltsgruppen mit einer ruhigen Oberfläche abgrenzen.

**Varianten:** `.core-ledger-card` für einen unabhängigen Block mit Titel und gegebenenfalls eigener Aktion; `.core-ledger-panel` für eine kompakte Gruppierung ohne Kartenwirkung.

**Eingaben:** Semantisches `article` oder `section`, eine echte Überschrift und der fachlich zusammengehörige Inhalt.

**Regeln:** Flache Struktur, keine dekorativen Schatten und keine verschachtelten Karten. Abschnittsüberschriften verwenden die gemeinsame `title-sm`-Typografie.

**Nicht verwenden:** Als Standardhülle um jedes Feld, jede Tabellenzeile oder jeden Seitenabschnitt.

```django
<article class="core-ledger-card">
    <header class="core-ledger-card__header">
        <h2 class="core-ledger-card__title">Offener Buchungszeitraum</h2>
    </header>
    <p>3. Quartal 2026 · sieben Buchungen zu prüfen</p>
</article>
```

## Navigation

**Zweck:** Stabile Orientierung zwischen den Hauptbereichen der neuen Buchhaltung.

**Varianten:** Vollständige Sidebar ab 1280 px, kompakte Icon-Leiste zwischen 768 und 1279 px und mobile Navigation unter 768 px. Sie werden zentral durch `new_ui/base.html` bereitgestellt.

**Eingaben:** Jeder Link braucht Bootstrap-Icon, sichtbares deutsches Kurzlabel und für den aktuellen Bereich `aria-current="page"`. Im kompakten Zustand bleiben zugänglicher Name und Tooltip erhalten.

**Regeln:** Bereiche, Reihenfolge und Beschriftungen bleiben zwischen Seiten stabil. Die Showcase-Seite erhält bewusst keinen normalen Navigationseintrag.

**Nicht verwenden:** Für Seitenaktionen, kontextabhängige Befehle oder immer neue fachliche Untervarianten.

```django
<a class="core-ledger-nav__link" href="{% url 'bookkeeping_overview' %}" aria-current="page">
    <i class="bi bi-journal-text" aria-hidden="true"></i>
    <span>Buchungen</span>
</a>
```

## Zugänglichkeit und Abnahme

- Alle Aktionen müssen per Tastatur erreichbar sein und den gemeinsamen sichtbaren Fokus zeigen.
- Symbole sind bei vorhandenem Text dekorativ (`aria-hidden="true"`); reine Symbolaktionen erhalten einen zugänglichen Namen.
- Status, Auswahl, Fehler und Erfolg verlassen sich nie allein auf Farbe.
- Inhalts- und Komponentenänderungen werden in der Showcase-Seite bei Mobil-, Tablet- und Desktopbreite geprüft.
- Eine fehlende legitime Variante wird zuerst im gemeinsamen System, in dieser Dokumentation und im Showcase ergänzt – nicht lokal auf einer Fachseite.
