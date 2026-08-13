---
name: Quintus Professional Ledger
version: 1.2
status: Production Ready
---

# Quintus Buchhaltung – Design System

## Vision

Quintus Buchhaltung ist eine kompakte professionelle Arbeitsoberfläche für Finanzprozesse.

Das Interface priorisiert:

- Informationsdichte
- schnelle Erfassbarkeit
- klare Aktionshierarchie
- Datensicherheit
- visuelle Ruhe
- konsistente Bedienmuster

Quintus ist ein Werkzeug für Experten, kein Marketing-Produkt. Die Oberfläche soll wie hochwertige Desktop-/Enterprise-Buchhaltungssoftware wirken: präzise, ruhig, kompakt und verlässlich.

## Technische Neutralität

Dieses Design-System definiert das visuelle Ergebnis, nicht das verwendete CSS-Framework.

Die bestehende Anwendung verwendet Django, Bootstrap und eigenes CSS. Begriffe oder Klassen aus Tailwind, Material Design oder anderen Frameworks sind keine Implementierungsvorgabe.

Bestehende technische Strukturen sollen weiterverwendet werden. Neue CSS- oder JavaScript-Frameworks dürfen nicht allein zur Umsetzung dieses Designs eingeführt werden.

## Typografie

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
    section-title: 16px
    page-title: 20px

  line-heights:
    compact: 1.25
    normal: 1.4
```

### Typografie-Regeln

- Standardtext und Tabelleninhalt: 14px, Gewicht 400.
- Sekundärinformationen und Meta-Daten: 12–13px.
- Tabellenkopf und Labels: 12–13px, Gewicht 600.
- Section Titles: 16px, Gewicht 600.
- Page Title: 20px, Gewicht 600.
- Keine überdimensionierten Überschriften.
- Monospace-Schriften nur verwenden, wenn technische IDs oder Codes dadurch nachweislich besser lesbar werden.
- Keine externe Font-Abhängigkeit hinzufügen, wenn Hanken Grotesk nicht bereits im Projekt verfügbar ist. In diesem Fall den definierten Fallback verwenden.

## Farben

```yaml
colors:
  structure:
    primary: '#1a365d'
    primary-hover: '#142b4b'
    on-primary: '#ffffff'

    secondary: '#eff4ff'
    on-secondary: '#1a365d'

  surfaces:
    background: '#f8f9ff'
    surface: '#ffffff'
    surface-muted: '#f8fafc'
    surface-hover: '#f1f5f9'

  borders:
    border: '#e2e8f0'
    border-strong: '#cbd5e0'

  text:
    text: '#1a202c'
    text-muted: '#64748b'

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

- Navy `#1a365d` ist die zentrale Strukturfarbe.
- Navy wird primär für Sidebar, aktive globale Orientierung und Primary Actions verwendet.
- Große Datenflächen und Tabellen bleiben hell.
- Prozessstatus und finanzielle Richtung sind strikt getrennte Semantiken.
- Eine Ausgabe ist kein Fehler.
- Eine Einnahme ist nicht automatisch ein Prozess-Erfolg.
- Rot wird für Fehler nur über die Prozessstatus-Tokens verwendet.
- Statusdarstellungen bevorzugen helle Hintergründe mit dunkler Schrift statt vollflächig gesättigter Badges.

## Geometry

```yaml
geometry:
  radius-default: 4px
  radius-navigation-active: 8px
  border-width: 1px
```

### Geometry-Regeln

- 4px ist der globale Standard für Buttons, Inputs, Cards, Dropdowns, Tabellencontainer und Modals.
- 8px ist ausschließlich für aktive Sidebar-/Navigationselemente vorgesehen.
- Keine allgemeine Radius-Skala mit zusätzlichen Größen.
- Keine stark gerundeten SaaS-Komponenten.
- Status-Badges kompakt und leicht gerundet; keine zwingende Pill-Form.

## Spacing & Density

```yaml
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px

layout:
  sidebar-width: 260px
  topbar-height: 48px
  main-margin: 24px
  gutter: 16px
```

### Density-Regeln

- Die Anwendung bleibt bewusst kompakt.
- Typische Innenabstände liegen bei 8–16px.
- 24px wird für größere Abschnittstrennung verwendet, nicht als Standard-Padding jeder Komponente.
- Keine unnötig großen Leerflächen.
- Keine fixen überhöhten Tabellenzeilen.
- Tabellenzeilen sollen typischerweise etwa 36–40px hoch wirken, abhängig vom Inhalt.

## Seitenstruktur

- Pro Screen existiert genau ein primärer Page Title.
- Eine globale Topbar darf den Seitentitel nicht wiederholen.
- Titel und optionale Beschreibung bilden eine kompakte Page-Header-Einheit.
- Primäre Aktionen werden in unmittelbarer Nähe des Page Headers oder des betroffenen Arbeitsbereichs platziert.
- Seltene oder destruktive Aktionen dürfen visuell zurückgenommen oder unter „Weitere Aktionen“ gruppiert werden.
- Große Datenansichten dürfen die normale Contentbreite sinnvoll ausnutzen.
- Breite Tabellen dürfen horizontal scrollen, statt fachlich relevante Spalten künstlich zu quetschen.
- Keine pauschale Umwandlung von Tabellen in Card-Listen auf Mobile.

## Komponentenstandards

### Sidebar

```yaml
sidebar:
  background: '#1a365d'
  text: '#ffffff'
  item-active-background: '#eff4ff'
  item-active-text: '#1a365d'
  item-radius: 8px
  item-margin: 8px
```

- Sidebar bleibt visuell stabil und zurückhaltend.
- Aktiver Menüpunkt muss klar erkennbar sein.
- Keine zusätzlichen Navigationseinträge allein wegen eines Mockups hinzufügen.

### Tabellen

```yaml
tables:
  header-background: '#f8fafc'
  header-text: '#64748b'
  header-weight: 600
  row-border: '#f1f5f9'
  hover-background: '#f8fafc'
```

Regeln:

- Heller, dezenter Tabellenkopf.
- Keine vollflächigen Navy-Tabellenheader.
- Keine vertikalen Zellrahmen.
- Kein Zebra-Striping.
- Dezente horizontale Trennlinien.
- Subtiles Row-Hover.
- Hohe Informationsdichte.
- Text linksbündig.
- Beträge rechtsbündig.
- Datumswerte möglichst einzeilig.
- Status als Badge, nicht als Button.
- Aktionen in Tabellen kompakt.
- Wenn das bestehende Bookkeeping die Aktionsspalte links verwendet, bleibt sie links.
- Buchungsdetails unter einer Banktransaktion werden eingerückt und visuell als Detailzeilen dargestellt.
- Keine Card um jede Tabelle, wenn die Tabelle bereits ausreichend strukturiert ist.

### Buttons

#### Primary

- Navy-Hintergrund.
- Weiße Schrift.
- 4px Radius.
- Kompakte Höhe.
- Nur für die wichtigste Aktion eines Bereichs.

#### Secondary

- Weißer oder heller Hintergrund.
- Dezenter Rahmen.
- Dunkle Schrift.
- Darf visuell nicht mit Primary konkurrieren.

#### Tertiary / Ghost

- Keine dominante Fläche.
- Für Abbrechen, zusätzliche Navigation oder „Weitere Aktionen“.

#### Danger

- Nur für tatsächlich destruktive Aktionen.
- Nicht für normale Warnungen oder finanzielle Ausgänge verwenden.

#### Icon Actions

- Kompakt und visuell zurückhaltend.
- Einheitliche Icon-Größe und Reihenfolge innerhalb gleicher Tabellen.
- Jede Icon-only Action benötigt zwingend `aria-label` und Tooltip/`title`.

### Formulare

- Weiße Eingabeflächen mit 1px neutralem Rahmen.
- 4px Radius.
- Kompakte Höhe und Abstände.
- Klare Labels.
- Fokuszustand deutlich, aber nicht dekorativ übertrieben.
- Validierungsfehler unmittelbar am betroffenen Feld.
- Read-only-Informationen bevorzugt als normale Werte darstellen, nicht als deaktivierte Inputs.
- Inputs, Selects und Textareas verwenden dieselbe visuelle Sprache.
- Keine überdimensionierten Formularelemente.

### Cards und Container

- Cards nur verwenden, wenn sie Informationen tatsächlich gruppieren.
- Weißer Hintergrund.
- Dezenter 1px-Rahmen.
- 4px Radius.
- Keine oder nur minimale Elevation.
- Keine verschachtelten Cards ohne fachlichen Mehrwert.
- Kompakte Innenabstände.

### Statusanzeigen

- Status-Badges verwenden die definierten Prozessstatus-Tokens.
- Finanzielle Richtung verwendet ausschließlich `incoming` bzw. `outgoing`.
- Finanzielle Richtung und Prozessstatus dürfen gleichzeitig darstellbar bleiben.
- Statusanzeigen sind nicht interaktiv, sofern keine tatsächliche Aktion dahintersteht.

### Dropdowns / Action Menus

- Weißer Hintergrund.
- 1px neutraler Rahmen.
- 4px Radius.
- Kompakte Menüeinträge.
- Dezenter Hover-Zustand.
- Destruktive Aktionen durch Separator oder Abstand von normalen Aktionen trennen.

## Accessibility

- Icon-only Actions benötigen immer `aria-label` und Tooltip/`title`.
- Fokuszustände müssen klar sichtbar sein.
- Farbe darf niemals das einzige Mittel zur Statuskommunikation sein.
- Interaktive Elemente müssen als solche erkennbar sein.
- Kontrast muss auch bei kleinen Tabellen- und Labeltexten ausreichend sein.

## Funktionale Abgrenzung

Elemente aus Mockups wie:

- Notifications
- Help
- User Menu
- Settings
- Logout
- zusätzliche Navigationseinträge
- zusätzliche Toolbar-Aktionen

sind **keine funktionalen Anforderungen**.

Sie werden nur implementiert, wenn die Anwendung die entsprechende Funktion bereits besitzt oder die Funktion ausdrücklich beauftragt wurde.

Das Design-System definiert ausschließlich die Gestaltung vorhandener bzw. beauftragter Funktionen.

## Anti-Patterns

Vermeiden:

- große Rundungen
- große Leerflächen
- überdimensionierte Überschriften
- starke Schatten
- Farbverläufe
- Glassmorphism
- Hero-Bereiche
- dekorative UI-Elemente ohne funktionalen Nutzen
- übermäßigen Einsatz der Primary-Farbe
- Navy-Header auf jeder Tabelle
- Zebra-Striping
- große Marketing-/CTA-Buttons
- mehrere konkurrierende Hauptaktionen
- unterschiedliche Designstile zwischen Screens
- neue UI-Frameworks nur zur Designumsetzung
- Tailwind-, Material- oder andere Framework-Begriffe als Designvorgabe
- Fake-Funktionen aus Mockups

## Implementierungsregel

Bei visuellen Entscheidungen gilt:

1. Diese `DESIGN.md`
2. bereits korrekt nach diesem Design umgesetzte Quintus-Seiten
3. bestehende wiederverwendbare CSS-Komponenten

Bei Usability und Interaktion gilt:

1. `docs/bookkeeping-ui-guidelines.md`
2. bestehende fachliche Bookkeeping-Workflows
3. vorhandene gute Referenzseiten

Wenn ein Mockup mit einer bestehenden fachlich sinnvollen UX-Regel kollidiert, bleibt die UX-Regel erhalten und nur das visuelle Erscheinungsbild wird übernommen.

Bestehendes Django-/Bootstrap-/CSS-Fundament wird weiterverwendet. Ein neues Framework darf nicht eingeführt werden, solange dies nicht ausdrücklich beauftragt ist.
