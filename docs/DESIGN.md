---
name: Quintus Application Design System
version: 2.0
status: Production Reference
reference: Quintus Hausverwaltung
---

# Quintus – Design System

## 1. Zweck

Dieses Dokument definiert die gemeinsame visuelle Sprache aller Quintus-Module.
Die bestehende Hausverwaltungsoberfläche ist die verbindliche visuelle Referenz.

Bookkeeping, Edikte und spätere Module erhalten keine eigene Designwelt. Sie
verwenden dieselbe Anwendungshülle, Typografie, Farbwelt, Tabellen, Formulare und
Aktionsmuster. Modulspezifische Komponenten werden nur ergänzt, wenn sie für den
jeweiligen Arbeitsablauf fachlich notwendig sind.

Quintus ist eine kompakte professionelle Arbeitsoberfläche. Das Design
priorisiert:

- schnelle Erfassbarkeit
- hohe, aber kontrollierte Informationsdichte
- klare Aktionshierarchie
- verlässliche Statuskommunikation
- visuelle Ruhe
- konsistente Bedienmuster

Quintus ist kein Marketing-Produkt und kein generisches SaaS-Dashboard.

## 2. Verbindliche Referenz und Priorität

Bei visuellen Entscheidungen gilt diese Reihenfolge:

1. bestehende, funktionierende Hausverwaltungsseiten
2. dieses `DESIGN.md`
3. bestehende wiederverwendbare Quintus-Komponenten und CSS-Regeln
4. neue Mockups oder generierte Entwürfe

Die Hausverwaltungsseiten definieren insbesondere:

- dunkelblaue, stabile Sidebar
- blau hervorgehobene aktive Navigation
- kräftig blauen primären Aktionsbutton
- helle, flächige Arbeitsbereiche
- kompakte Tabellen mit horizontalen Trennlinien
- kleine, klar umrissene Tabellenaktionen
- zurückhaltende Statusfarben

Bestehende Bookkeeping-Screens sind eine Referenz für benötigte Daten und
Funktionen, nicht automatisch für Navigation, Seitenaufbau oder
Informationshierarchie.

## 3. Technische Neutralität

Das Design-System definiert das visuelle und interaktive Ergebnis, nicht das
CSS-Framework.

Die bestehende Anwendung verwendet Django, Bootstrap und eigenes CSS. Diese
Basis wird weiterverwendet. Neue CSS- oder JavaScript-Frameworks werden nicht
allein zur Designumsetzung eingeführt.

Von Stitch oder anderen Werkzeugen erzeugter Code ist Entwurfs- und
Referenzmaterial. Er wird nicht ungeprüft in die produktive Anwendung kopiert.

## 4. Typografie

```yaml
typography:
  font-family: "'Hanken Grotesk', 'Segoe UI', Arial, sans-serif"
  weights:
    normal: 400
    medium: 500
    semibold: 600
    bold: 700
  sizes:
    label: 12px
    small: 13px
    body: 14px
    section-title: 17px
    page-title: 22px
  line-heights:
    compact: 1.25
    normal: 1.4
```

Regeln:

- Standardtext und Tabelleninhalt: 14px.
- Sekundärinformationen und Metadaten: 12–13px.
- Tabellenkopf und Labels: 12–13px, Gewicht 600.
- Abschnittstitel: 16–18px, Gewicht 600.
- Seitentitel: 20–22px, Gewicht 600.
- Keine überdimensionierten Überschriften.
- Technische IDs dürfen bei echtem Lesbarkeitsgewinn monospace erscheinen.
- Wenn Hanken Grotesk nicht lokal vorhanden ist, wird kein zusätzlicher externer
  Font-Dienst eingeführt; stattdessen gilt der definierte Fallback.

## 5. Farben

```yaml
colors:
  structure:
    primary: '#1a365d'
    primary-hover: '#142b4b'
    on-primary: '#ffffff'
    active-navigation: '#35577f'
    active-navigation-hover: '#3f638d'
    active-indicator: '#0d6efd'

  accent:
    action: '#0d6efd'
    action-hover: '#0b5ed7'
    action-foreground: '#ffffff'
    selection: '#eaf2ff'
    focus: '#86b7fe'
    accent-surface: '#f5f9ff'
    accent-surface-strong: '#eaf2ff'
    accent-border: '#bfdbfe'
    accent-hover: '#edf5ff'

  surfaces:
    background: '#f4f7fb'
    topbar: '#ffffff'
    surface: '#ffffff'
    surface-muted: '#f8fafc'
    surface-hover: '#f1f5f9'

  borders:
    border: '#e2e8f0'
    border-strong: '#cbd5e1'

  text:
    text: '#172033'
    text-muted: '#64748b'
    text-on-dark: '#ffffff'
    text-on-dark-muted: '#c9d5e5'

  process-status:
    success:
      foreground: '#166534'
      background: '#f0fdf4'
      border: '#bbf7d0'
    warning:
      foreground: '#92400e'
      background: '#fffbeb'
      border: '#fde68a'
    error:
      foreground: '#b91c1c'
      background: '#fef2f2'
      border: '#fecaca'
    info:
      foreground: '#1e40af'
      background: '#eff6ff'
      border: '#bfdbfe'
    neutral:
      foreground: '#475569'
      background: '#f8fafc'
      border: '#e2e8f0'

  financial-direction:
    incoming:
      foreground: '#047857'
      background: '#ecfdf5'
    outgoing:
      foreground: '#be123c'
      background: '#fff1f2'
```

### Farbregeln

- Navy ist die Strukturfarbe für Sidebar, Marke und globale Orientierung.
- Kräftiges Blau ist die Akzentfarbe für primäre Aktionen, Auswahl und Fokus.
- Primäre Aktionsbuttons sind blau, nicht Navy.
- `accent-surface` strukturiert Einleitungs- und Informationsflächen sehr
  zurückhaltend; `accent-surface-strong` hebt klar abgegrenzte Unterbereiche und
  Tabellenköpfe hervor.
- `accent-border` kennzeichnet zugehörige Kanten und Rahmen. `accent-hover` ist
  ausschließlich für interaktive Hover-Zustände vorgesehen.
- Große Datenflächen und Tabellen bleiben hell.
- Farbe wird funktional eingesetzt, nicht dekorativ verteilt.
- Prozessstatus und finanzielle Richtung sind getrennte Semantiken.
- Eine Ausgabe ist kein Fehler; eine Einnahme ist nicht automatisch ein Erfolg.
- Status verwendet bevorzugt helle Hintergründe mit dunkler Schrift.
- Farbe ist nie das einzige Mittel zur Statuskommunikation.

## 6. Geometrie, Abstände und Dichte

```yaml
geometry:
  radius-default: 4px
  radius-navigation: 6px
  border-width: 1px

spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px

layout:
  sidebar-width: 220px
  topbar-height: 52px
  main-margin: 20px
  gutter: 16px
```

Regeln:

- Die Anwendung bleibt bewusst kompakt.
- Typische Innenabstände liegen zwischen 8 und 16px.
- 24px dient der Trennung größerer Abschnitte.
- Tabellenzeilen wirken typischerweise 36–42px hoch, abhängig vom Inhalt.
- Es gibt keine künstlich großen Leerflächen innerhalb von Komponenten.
- Leere Seitenfläche unter kurzen Tabellen ist zulässig und wird nicht mit
  wertlosen Kennzahlen oder Dekoration gefüllt.
- 4px ist der Standardradius für Buttons, Inputs, Cards, Tabellencontainer und
  Modals.
- Keine stark gerundeten SaaS-Komponenten und keine Pill-Optik als Standard.

## 7. Anwendungshülle

### Sidebar

- Die Sidebar ist dunkelblau und bleibt über alle Module identisch.
- Logo und `QUINTUS` stehen am oberen Rand; die Modulbezeichnung darf darunter
  kompakt erscheinen, beispielsweise `BUCHHALTUNG`.
- Hauptbereiche werden logisch gruppiert.
- Der aktive Haupteintrag erhält einen mittelblauen Hintergrund, weiße Schrift
  und einen schmalen kräftig blauen Indikator am linken Rand.
- Untermenüs sind eingerückt und nur bei Bedarf geöffnet.
- Zähler erscheinen als kompakte Badges am rechten Rand.
- Interne technische Zustände werden nicht automatisch zu Hauptnavigation.
- Mit zusätzlichen Modulen muss die Sidebar scrollbar bleiben und Gruppen
  müssen einklappbar sein.

### Topbar und Breadcrumbs

- Die Topbar ist weiß, kompakt und durch eine dezente Unterkante getrennt.
- Sie enthält globale Orientierung oder Breadcrumbs, nicht dieselbe Überschrift
  ein zweites Mal.
- Ein Breadcrumb darf den aktuellen Bereich nennen; der eigentliche Seitentitel
  steht ausschließlich im Inhaltsbereich.
- Nicht vorhandene Funktionen wie Benachrichtigungen, Hilfe oder Benutzerkonto
  werden nicht als Dekoration ergänzt.

### Seitenkopf

- Jede Seite besitzt genau einen sichtbaren Seitentitel.
- Optionale Beschreibung und Metadaten stehen direkt darunter.
- Die primäre Aktion steht rechts auf derselben visuellen Ebene wie der Titel.
- Zeitraumwahl, Filter oder Ansichtsumschalter stehen kompakt unterhalb des
  Titels oder direkt über dem betroffenen Inhalt.

## 8. Navigation und Informationsarchitektur

Die Navigation benennt Arbeitsbereiche und Benutzeraufgaben, nicht sämtliche
Backend-Status.

Status wie `offen`, `zugeordnet`, `buchungsfertig` oder `exportiert` dürfen als
Filter, Badge oder Abschnitt erscheinen. Ein eigener Navigationseintrag ist nur
gerechtfertigt, wenn dahinter eine eigenständige Benutzeraufgabe liegt.

Für Bookkeeping wird die endgültige Navigation aus getesteten Arbeitsabläufen
abgeleitet. Die aktuelle Navigation ist funktionale Bestandsaufnahme, keine
unveränderbare Vorgabe.

## 9. Tabellen

```yaml
tables:
  header-background: '#f8fafc'
  header-text: '#334155'
  header-weight: 600
  row-border: '#e8edf4'
  hover-background: '#f8fafc'
```

Regeln:

- Heller, dezenter Tabellenkopf.
- Keine vollflächigen Navy-Tabellenheader.
- Keine vertikalen Zellrahmen und kein Zebra-Striping.
- Dezente horizontale Trennlinien und subtiles Row-Hover.
- Text linksbündig, Beträge rechtsbündig.
- Datumswerte möglichst einzeilig.
- Status ist ein Badge, kein Button.
- Aktionsspalte steht links, wenn der Arbeitsablauf mit einer Zeilenaktion
  beginnt.
- Bearbeiten erscheint neutral; Löschen erscheint als zurückhaltende
  Danger-Outline-Aktion und benötigt eine Bestätigung.
- Seltene oder destruktive Aktionen können in `Weitere Aktionen` liegen.
- Breite Tabellen dürfen horizontal scrollen.
- Tabellen werden auf schmalen Ansichten nicht pauschal in Karten umgewandelt.
- Buchungsdetails unter einer Transaktion werden eingerückt und als
  untergeordnete Detailzeilen dargestellt.
- Sortierung und Filter werden ergänzt, sobald Umfang oder Arbeitsaufgabe sie
  erfordern; nicht jede kleine Stammdatentabelle braucht eine Toolbar.

## 10. Buttons und Aktionen

### Primary

- Kräftig blauer Hintergrund, weiße Schrift, 4px Radius.
- Nur für die wichtigste Aktion eines Bereichs.
- Beschriftung beschreibt das Ergebnis, beispielsweise `Neue Liegenschaft`,
  `Buchung abschließen` oder `Übergabepaket herunterladen`.

### Secondary

- Weißer oder heller Hintergrund, neutraler Rahmen, dunkle Schrift.
- Darf visuell nicht mit Primary konkurrieren.

### Tertiary / Ghost

- Keine dominante Fläche.
- Für Abbrechen, ergänzende Navigation und seltene Aktionen.

### Danger

- Nur für tatsächlich destruktive Aktionen.
- Rot wird nicht für normale Warnungen oder finanzielle Ausgänge missbraucht.

### Icon Actions

- Kompakt, einheitliche Größe und Reihenfolge.
- Jede Icon-only Action benötigt `aria-label` und Tooltip bzw. `title`.
- Das Icon muss die Aktion ausreichend verständlich darstellen; andernfalls wird
  eine Textbeschriftung verwendet.

## 11. Formulare

- Weiße Eingabeflächen mit neutralem 1px-Rahmen und 4px Radius.
- Kompakte Höhe und klare Labels.
- Fokuszustand verwendet die Akzentfarbe und ist deutlich sichtbar.
- Validierungsfehler stehen unmittelbar am betroffenen Feld.
- Read-only-Informationen erscheinen als normale Werte, nicht als deaktivierte
  Inputs.
- Eingaben, Selects und Textareas verwenden dieselbe visuelle Sprache.
- Lange fachliche Formulare werden nach Entscheidungen gegliedert; nicht alle
  Felder werden ohne Priorität gleichzeitig präsentiert.
- Pro Arbeitsbereich gibt es eine klar erkennbare Hauptaktion.

### Verwaltungs-CRUD mit Tabellenfokus

- Die Listenansicht ist die stabile Hauptansicht und zeigt Suche, primäre
  Anlageaktion, Datentabelle und eine echte Ergebnisanzahl in einem
  zusammenhängenden Bereich.
- Anlage, Bearbeitung, Versionierung und Löschbestätigung dürfen als kompakte
  Modals über der Liste erscheinen, wenn der Benutzer dadurch Orientierung und
  Suchkontext behält.
- Validierungsfehler öffnen dasselbe Modal erneut und erhalten alle Eingaben;
  Dialogtitel und Hauptaktion benennen den jeweiligen Vorgang eindeutig.
- Modals enthalten sämtliche fachlich notwendigen Felder. Historische oder
  versionierte Datensätze werden nicht direkt überschrieben; der Dialog folgt
  immer der bestehenden Versionierungslogik.
- Fachlich zusammengehörige Unterformulare werden durch `accent-surface` und
  `accent-border` gegliedert, nicht durch verschachtelte Cards.
- Modals sind per Tastatur schließbar, halten den Fokus während der Bedienung im
  Dialog und führen nach Abbruch verlässlich zur Listenansicht zurück.
- Destruktive Aktionen benötigen eine eigene Bestätigung. Die Bestätigung nennt
  das betroffene Objekt und weist auf die fehlende Rückgängig-Funktion hin.

## 12. Cards und Kennzahlen

- Cards gruppieren Informationen nur bei echtem fachlichem Zusammenhang.
- Weißer Hintergrund, dezenter Rahmen, 4px Radius, keine oder minimale Elevation.
- Keine verschachtelten Cards ohne Mehrwert.
- Kennzahlen müssen eine Entscheidung oder nächste Aktion unterstützen.
- Leere Diagramme und Kennzahlen ohne Handlungswert werden ausgeblendet oder
  durch einen kompakten Leerzustand ersetzt.
- Ein Dashboard ist keine Sammlung gleichgewichteter Kennzahlen.
- Warnungen, offene Arbeit und notwendige Entscheidungen stehen vor rein
  informativen Statistiken.
- Diagramme werden nur verwendet, wenn ein Trend oder Vergleich visuell leichter
  erfassbar ist als in Text oder Tabelle.

## 13. Status und Meldungen

- Status-Badges verwenden die definierten Prozessstatus-Tokens.
- Finanzielle Richtung verwendet ausschließlich `incoming` oder `outgoing`.
- Finanzielle Richtung und Prozessstatus dürfen gleichzeitig sichtbar sein.
- Warnungen erklären Problem und notwendige Aktion.
- Fehlende Daten, Duplikate und technische Fehler werden sprachlich
  unterschieden.
- Statusanzeigen sind nicht interaktiv, sofern keine Aktion dahintersteht.

## 14. Bookkeeping-spezifische Komponenten

Bookkeeping erweitert das globale System nur um fachliche Arbeitskomponenten:

- Banktransaktionskopf
- Paperless-Beleganzeige
- Buchungsvorschlag und Buchungszeilen
- Split-Buchungen
- Prüf- und Vollständigkeitsstatus
- Periodenauswahl
- Bankabstimmung
- Quartals- bzw. Übergabeabschluss

### Bookkeeping-Arbeitsseiten

- Transaktion, Beleg und Buchungsdaten werden in einem zusammenhängenden
  Arbeitsbereich dargestellt.
- Der Benutzer muss nicht zwischen Statusseiten wechseln, um einen Vorgang zu
  verstehen oder abzuschließen.
- Interne Statusbegriffe werden nur gezeigt, wenn sie für die Entscheidung
  relevant sind.
- Nach Abschluss eines Vorgangs kann direkt der nächste offene Vorgang geöffnet
  werden.
- Übersichten dienen dem Finden und Priorisieren; die eigentliche Bearbeitung
  erfolgt in einer klaren Arbeitsansicht.

### Dashboard

- Das Dashboard zeigt offene Arbeit, Blockaden und die nächste sinnvolle Aktion.
- Finanzdiagramme erscheinen nur bei aussagekräftigen Daten.
- Karten ohne verwertbaren Inhalt werden nicht allein zur Flächenfüllung gezeigt.
- Zeitraumwahl bleibt kompakt und konsistent.

### Periodenabschluss

- Vollständigkeit, Bankabstimmung, fehlende Belege und Exportbereitschaft werden
  in einer klaren Reihenfolge dargestellt.
- Eine Vielzahl gleich aussehender Kennzahlenkarten wird vermieden.
- Die primäre Abschluss- oder Übergabeaktion ist erst dann dominant, wenn die
  Voraussetzungen verständlich dargestellt sind.

## 15. Accessibility

- Icon-only Actions besitzen `aria-label` und Tooltip bzw. `title`.
- Fokuszustände sind klar sichtbar.
- Farbe ist nie das einzige Mittel zur Statuskommunikation.
- Interaktive Elemente sind als solche erkennbar.
- Kontrast ist auch bei kleinen Tabellen- und Labeltexten ausreichend.
- Tastaturbedienung und logische Fokusreihenfolge werden bei Arbeitsformularen
  geprüft.

## 16. Stitch-Regeln

Bei Entwürfen in Stitch gilt:

- Ein Screenshot der Hausverwaltung wird als visuelle Referenz mitgegeben.
- Dieses `DESIGN.md` wird als Designsystem verwendet.
- Stitch gestaltet nur den beauftragten Arbeitsbereich, nicht automatisch die
  globale Sidebar oder Marke neu.
- Entwürfe verwenden realistische deutschsprachige Beispieldaten.
- Varianten unterscheiden sich im Bedienkonzept, nicht nur in Farben.
- Keine Fake-Funktionen, zusätzlichen Menüpunkte oder dekorativen Toolbars.
- Die Ausgabe ist ein UX- und Layoutentwurf; die produktive Umsetzung erfolgt im
  vorhandenen Django-/Bootstrap-/CSS-Fundament.

## 17. Anti-Patterns

Vermeiden:

- große Rundungen und Pill-Optik
- starke Schatten oder Farbverläufe
- Glassmorphism
- Hero-Bereiche
- dekorative UI ohne funktionalen Nutzen
- übermäßigen Einsatz von Navy oder Akzentblau
- Navy-Header auf jeder Tabelle
- Zebra-Striping
- große Marketing-CTA-Buttons
- mehrere konkurrierende Hauptaktionen
- unterschiedliche Designstile zwischen Modulen
- Navigation nach jedem internen Backend-Status
- Dashboards mit leeren oder nicht handlungsrelevanten Karten
- neue Frameworks allein zur Designumsetzung
- ungeprüfte Übernahme generierten Codes
- Fake-Funktionen aus Mockups

## 18. Implementierungsregel

Bei visuellen Entscheidungen gilt:

1. vorhandene gute Hausverwaltungsseiten
2. dieses `DESIGN.md`
3. bestehende wiederverwendbare Quintus-Komponenten

Bei Usability und Interaktion gilt:

1. beobachtete reale Benutzeraufgaben
2. dokumentierte fachliche Workflows
3. getestete Quintus-Arbeitsseiten
4. Mockups und generierte Entwürfe

Wenn ein Mockup mit einer fachlich sinnvollen und getesteten UX-Regel
kollidiert, bleibt die UX-Regel erhalten. Wenn eine bestehende Seite lediglich
historisch gewachsen ist, gilt sie nicht automatisch als UX-Vorgabe.

Das bestehende Django-/Bootstrap-/CSS-Fundament wird weiterverwendet. Neue
Frameworks werden nur nach ausdrücklicher Entscheidung eingeführt.
