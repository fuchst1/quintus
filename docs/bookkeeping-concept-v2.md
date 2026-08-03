# Konzept V2: Automatisierte Quartalsbuchhaltung in Quintus

**Zielsystem:** Django-Projekt `quintus`  
**Neue Django-App:** `bookkeeping`  
**Optionale Integrations-App:** `bookkeeping_property_bridge`  
**Stand:** 03.08.2026  
**Mandant im MVP:** Immo-Fuchs KG

## 1. Entscheidung in Kurzform

Die automatische Buchhaltung wird als **eigenständige Django-App `bookkeeping` innerhalb des bestehenden Projekts `quintus`** umgesetzt. Sie ist fachlich und technisch von der Hausverwaltung getrennt und erhält eine **vollständig eigene Benutzeroberfläche**.

Bookkeeping hat einen eigenen Einstieg, ein eigenes Dashboard, eine eigene Navigation, eigene Templates und eigene statische Assets. Die Oberfläche der Hausverwaltung wird weder eingebettet noch erweitert. Im Hausverwaltungsmenü muss kein Link zu Bookkeeping vorhanden sein. Gemeinsam genutzt werden dürfen im Hintergrund nur technische Quintus-Komponenten wie Benutzerkonten, Berechtigungen, Deployment und Logging.

Die Hausverwaltung bleibt führend für Liegenschaften, Einheiten, Personen und Mietverhältnisse. Bookkeeping darf ausgewählte Daten wie Mietername, IBAN, Zuordnung zur Einheit und erwartete Mietbestandteile **nur lesend über eine klar definierte Schnittstelle** nutzen. Die Buchhaltungs-App hat keine direkten Foreign Keys auf Hausverwaltungsmodelle und funktioniert auch ohne diese Schnittstelle.

Für eine nachvollziehbare Buchung speichert Bookkeeping zum Zeitpunkt des Matchings einen kleinen, unveränderlichen Snapshot der tatsächlich verwendeten Informationen. Dadurch ändern spätere Korrekturen eines Mieters oder Mietvertrags keine bereits freigegebene Buchung.

## 2. Ziel und Abgrenzung

### 2.1 Ziel

Der bisher manuelle Quartalsprozess wird weitgehend vorbereitet:

1. Bankbewegungen aus JSON oder OFX importieren.
2. Belege in paperless-ngx finden oder dorthin hochladen.
3. Kategorie, USt-Symbol, Geschäftspartner und Kostenstelle vorschlagen.
4. Bankbewegungen bei Bedarf auf mehrere Buchungszeilen aufteilen.
5. Den Benutzer alle Vorschläge prüfen und freigeben lassen.
6. Freigegebene Buchungen in eine unveränderte Kopie der Steuerberater-Vorlage exportieren.
7. Zugehörige Belege und Kontoauszüge als reproduzierbares Quartalspaket bereitstellen.

### 2.2 Nicht Teil des MVP

- keine doppelte Buchhaltung und kein Hauptbuchersatz
- keine eigenständige UVA- oder Steuerberechnung außerhalb der Excel-Vorlage
- kein Zahlungsverkehr und keine Bank-API mit Schreibzugriff
- keine automatische Freigabe durch Regeln oder KI
- keine Mietvertrags-, Betriebskosten- oder Eigentümerverwaltung
- keine Änderung von Hausverwaltungsdaten aus Bookkeeping
- keine Einbettung in Dashboard, Menü oder Seitenlayout der Hausverwaltung
- kein Ersatz für die abschließende Prüfung durch Steuerberater oder Benutzer

## 3. Fachliche Systemgrenze

### 3.1 Datenhoheit

| Daten | Führendes System | Verwendung in Bookkeeping |
|---|---|---|
| Mandant, Bankkonten, Kontenplan, Buchungen | Bookkeeping | vollständig |
| Lieferanten und sonstige Geschäftspartner | Bookkeeping | vollständig |
| Liegenschaften, Einheiten, Personen, Mietverträge | Hausverwaltung | nicht duplizieren |
| Mieter-IBAN, erwartete Mietzahlung, Einheit | Hausverwaltung | optionaler, lesender Matching-Input |
| Buchungsbelege und Kontoauszüge | paperless-ngx | Dokumentablage; Bookkeeping speichert Referenz und Prüfdaten |
| Steuerberater-Excel | versionierte Exportvorlage | Exportziel und Kontenplanquelle |

### 3.2 Welche Hausverwaltungsdaten sinnvoll sind

Für das Matching sind folgende Felder sinnvoll:

- stabile externe ID des Mietverhältnisses
- Anzeigename des Zahlers/Mieters
- normalisierte IBAN
- gültig von/bis
- Einheitencode als vorgeschlagene Kostenstelle
- erwarteter Gesamtbetrag und, wenn vorhanden, die Bestandteile HMZ, BK, Heizung und Parkplatz
- für die Bestandteile vorgesehene Kategorie bzw. USt-Behandlung

Nicht übertragen werden:

- Geburtsdatum
- Telefonnummer
- E-Mail-Adresse
- private Notizen
- vollständige Personenakte
- Dokumente ohne Buchhaltungsbezug

### 3.3 Technische Kopplung

`bookkeeping` kennt keine Modelle aus der Hausverwaltungs-App. Eine optionale App `bookkeeping_property_bridge` kennt beide Seiten und liefert ausschließlich eine definierte Projektion:

```text
Hausverwaltung
    │  nur lesen
    ▼
bookkeeping_property_bridge
    │  MatchingProfile DTO / Sync
    ▼
bookkeeping
```

Bookkeeping speichert `source_system`, `external_id`, `fetched_at` und einen Snapshot der für den Vorschlag verwendeten Werte. Es gibt keine direkte Datenbank-Fremdschlüsselbeziehung zur Hausverwaltung.

Wenn die Hausverwaltung später ersetzt oder abgeschaltet wird, kann der Bridge-Adapter entfernt werden. Manuelle Matching-Regeln und Geschäftspartner funktionieren weiterhin.

## 4. Verifizierte Eingabeformate

### 4.1 Bank-JSON

Die Datei `AT822011184722039000_2026-07-01_2026-07-31.json` enthält 24 Transaktionen.

Verifizierte Eigenschaften:

- `booking` und `valuation` sind bei allen Transaktionen vorhanden.
- `partnerName` und `partnerAccount.iban` sind bei allen 24 Transaktionen vorhanden.
- `referenceNumber` ist bei allen 24 Transaktionen vorhanden und innerhalb der Datei eindeutig.
- `transactionId`, `containedTransactionId` und `e2eReference` sind im Beispiel leer und daher nicht als Primärschlüssel geeignet.
- `reference` ist bei 10 von 24 Transaktionen leer.
- Beträge werden als Integer in `amount.value` gespeichert; `amount.precision = 2`. Beispiel: `12345` entspricht `123,45 EUR`.
- Die Währung ist im Beispiel durchgehend EUR.
- Ein Anfangs- oder Endsaldo ist im Beispiel nicht vorhanden.

Importregel für Beträge:

```text
dezimaler Betrag = amount.value / 10 ** amount.precision
```

Die Originaldatei, ihr SHA-256-Hash und die Parser-Version werden gespeichert. Die Rohdatei bleibt unverändert.

### 4.2 OFX

OFX bleibt ein Fallback. FITID wird als Quellreferenz genutzt. JSON und OFX derselben Kontobewegung dürfen nicht doppelt importiert werden; zusätzlich zur Quellreferenz wird daher ein technischer Transaktionsfingerprint gebildet.

### 4.3 Steuerberater-Excel

Die geprüfte Datei `EinnahmenAusgabenRechnung Immo-Fuchs KG 2026 Q2.xlsx` enthält sechs Sheets:

- `Allgemeines`
- `Eingaben`
- `Auswertung`
- `UVA`
- `CSV`
- `Kontenplan`

Das Sheet `Eingaben` hat 19 Spalten. Die Buchungsdaten beginnen in Zeile 8. Die Vorlage hält Buchungszeilen bis Zeile 1473 bereit.

#### Eingabespalten

| Spalte | Feld | Exportverhalten |
|---|---|---|
| A | Belegkreis | schreiben: `BK`, `KA` oder `PR` |
| B | Belg Nr | schreiben; derzeit Monatsnummer aus Zahlungsdatum |
| C | Datum der Bezahlung | schreiben |
| D | Text | schreiben |
| E | Re.Nr | schreiben, falls vorhanden |
| F | Lieferant/Kunde | schreiben |
| G | Einnahmen/Ausgaben Brutto | schreiben; Einnahme positiv, Ausgabe negativ |
| H | UST-Sym | schreiben: `0`, `10`, `13`, `20`, `IG`, `RC` |
| K | Kategorie | exakt nach `Kontenplan!D` schreiben |

Damit sind **neun** Buchungseingaben erforderlich: A bis H sowie K.

Die Spalten I, J und L bis S enthalten Formeln und dürfen nicht durch Werte überschrieben werden. Insbesondere referenziert das Sheet `CSV` die Spalte B; sie darf nicht ausgelassen werden.

Die Vorlage enthält außerdem:

- `G2`: Banksaldo zu Beginn
- `G3`: Kontrollsumme Bank, Formel
- `G4`: Kassastand zu Beginn
- `G5`: Kontrollsumme Kassa, Formel

Da das Beispiel-JSON keinen Saldo enthält, werden Anfangssaldo Bank und Kassa beim Export manuell eingegeben oder aus einer späteren verlässlichen Quelle übernommen. Der Benutzer bestätigt die Kontrollsummen vor Freigabe des Exportpakets.

`Kontenplan` hat in der geprüften Vorlage 994 Datenzeilen. Der Kategorie-Text in Spalte D ist der verbindliche Exportwert. Der Kontenplan wird pro Vorlagenversion importiert und nicht stillschweigend überschrieben.

#### Exportregeln

- Ausgangspunkt ist immer eine unveränderte, versionierte Kopie der Steuerberater-Vorlage.
- Es werden keine Zeilen oder Spalten eingefügt oder gelöscht.
- Es werden ausschließlich A–H und K in den vorgesehenen Buchungszeilen beschrieben.
- Formeln, Datenvalidierungen, Formatierung und die übrigen Sheets bleiben erhalten.
- Die maximale Anzahl verfügbarer Zeilen wird vor Export geprüft.
- Nach Export wird die Datei mit Excel oder LibreOffice neu berechnet und kontrolliert.
- Prüfsummen werden mit den freigegebenen Buchungen abgeglichen.
- Exportdatei, Vorlagen-Hash, Buchungs-IDs und Belegmanifest werden unveränderlich protokolliert.

## 5. Django-Architektur

### 5.1 Projektstruktur

```text
quintus/
├── manage.py
├── core/                           Django-Projektkonfiguration
├── webapp/                         bestehende Hausverwaltung
├── bookkeeping/                    neue, eigenständige Fach-App
│   ├── admin.py
│   ├── apps.py
│   ├── models/
│   ├── services/
│   │   ├── bank_import/
│   │   ├── matching/
│   │   ├── paperless/
│   │   └── export/
│   ├── templates/bookkeeping/
│   │   ├── base.html               eigenes Bookkeeping-Layout
│   │   ├── dashboard.html
│   │   ├── imports/
│   │   ├── transactions/
│   │   ├── documents/
│   │   ├── exports/
│   │   └── settings/
│   ├── static/bookkeeping/         eigenes CSS und JavaScript
│   ├── tests/
│   └── urls.py
└── bookkeeping_property_bridge/    optional; einzige Kopplungsstelle
```

### 5.2 Laufzeit und Deployment

Bookkeeping wird in die bestehende Quintus-Installation mit Python-Virtualenv, Gunicorn und systemd aufgenommen. Ein neuer Servername `sextus` und Docker Compose sind für diese Variante nicht vorgesehen.

Quintus verwendet derzeit SQLite. Für den manuellen MVP mit einem Benutzer und kurzen Transaktionen ist das grundsätzlich nutzbar. Vor parallelen Importjobs, Celery oder mehreren gleichzeitigen Benutzern wird das gesamte Quintus-Projekt kontrolliert auf PostgreSQL migriert. Eine separate PostgreSQL-Datenbank nur für eine App wird vermieden, solange kein zwingender Isolationsgrund besteht.

### 5.3 Gemeinsame Komponenten

Bookkeeping darf aus Quintus gemeinsam verwenden:

- Benutzeranmeldung und Berechtigungen
- zentrale Konfiguration, Logging und E-Mail-Versand
- Deployment und Backup-Mechanismus

Nicht gemeinsam verwendet werden:

- Basislayout, Dashboard, Navigation, CSS oder JavaScript der Hausverwaltung
- Hausverwaltungsmodelle als Bookkeeping-Datenmodell
- direkte Foreign Keys auf `webapp`
- Hausverwaltungsregeln für Buchung oder Steuer

### 5.4 Dedizierte Bookkeeping-Oberfläche

Die Benutzeroberfläche ist ein eigenständiger Arbeitsbereich. Sie wird unter einem eigenen URL-Namespace bereitgestellt, beispielsweise `/bookkeeping/`. Ein eigener Hostname oder eine Subdomain kann später ergänzt werden, ohne das fachliche Design zu ändern.

Nach dem Aufruf landet der Benutzer direkt im Bookkeeping-Dashboard. Es gibt keinen Wechsel in Hausverwaltungsseiten und keine Vermischung der Navigationen.

#### Hauptnavigation

| Bereich | Inhalt |
|---|---|
| Dashboard | aktuelles Quartal, offene Transaktionen, fehlende Belege, Prüffälle, letzter Export |
| Bankimporte | JSON/OFX hochladen, Vorschau, Importprotokoll, Duplikate |
| Transaktionen | alle Bankbewegungen, Status, Suche, Filter, ignorierte Bewegungen |
| Buchungen prüfen | Vorschläge, Split-Buchungen, USt, Kategorien, Kostenstellen, Freigabe |
| Belege | Paperless-Suche, Upload, Sync-Status, fehlende und mehrfach zugeordnete Belege |
| Exporte | Quartalsprüfung, Anfangssalden, Excel-Export, Belegpaket, Historie |
| Stammdaten | Mandanten, Bankkonten, Geschäftspartner, Kostenstellen, Kontenplanversionen |
| Regeln | Matching-Regeln, Prioritäten, Gültigkeit und Trefferhistorie |
| Integration | Status von Paperless und optionaler Hausverwaltungs-Bridge |

#### Dashboard

Das Dashboard zeigt nur buchhaltungsrelevante Informationen:

- ausgewählter Mandant und Zeitraum
- Anzahl offener, zu prüfender, freigegebener und exportierter Buchungen
- Summe und Anzahl noch nicht zugeordneter Banktransaktionen
- fehlende Belege und Paperless-Synchronisationsfehler
- Buchungen mit Betragsdifferenz, unbekannter Kategorie oder USt-Sonderfall
- Status des aktuellen Quartalsexports
- letzter Bankimport und dessen Ergebnis

#### Review-Arbeitsplatz

Die zentrale Seite ist keine gewöhnliche Django-Admin-Liste, sondern eine speziell gebaute Prüfoberfläche:

- links Banktransaktion und Verwendungszweck
- daneben gefundener oder hochgeladener Beleg
- darunter eine oder mehrere editierbare Buchungszeilen
- sichtbarer Abgleich zwischen Bankbetrag und Summe der Buchungszeilen
- Vorschlag, Konfidenz und nachvollziehbare Matching-Gründe
- Aktionen `Zurückstellen`, `Ignorieren`, `Geprüft` und `Freigeben`
- Tastaturbedienung für die wiederholte Quartalsarbeit

HTMX kann für Filter, Detailbereiche, Split-Zeilen und Statuswechsel verwendet werden. Die Oberfläche bleibt serverseitig gerendert und benötigt kein separates JavaScript-Frontend-Framework.

#### Administration

Auch Stammdaten und Regeln erhalten einfache Seiten innerhalb der dedizierten Oberfläche. Django Admin bleibt für technische Administration und Fehlerbehebung verfügbar, ist aber nicht die reguläre Arbeitsoberfläche für die Quartalsbuchhaltung.

#### Visuelle Trennung

- eigenes `bookkeeping/base.html`
- eigene Navigation und eigener Seitentitel
- eigener CSS-Namespace bzw. eigene statische Dateien
- keine Verwendung von `webapp/base.html`
- keine Links zurück zur Hausverwaltung, sofern sie nicht später ausdrücklich gewünscht werden
- Bookkeeping-Berechtigungen steuern den Zugang zum gesamten Arbeitsbereich

## 6. Rollen und Berechtigungen

| Rolle | Rechte |
|---|---|
| Bookkeeping Viewer | lesen, Exporte ansehen |
| Bookkeeping Editor | importieren, Vorschläge bearbeiten, Belege zuordnen |
| Bookkeeping Approver | prüfen, freigeben, zurückweisen |
| Bookkeeping Exporter | Exportvorgang erstellen und abschließen |
| Administrator | Stammdaten, Vorlagen, Regeln und Integration konfigurieren |

Im Einbenutzerbetrieb kann Thomas mehrere Rollen besitzen. Trotzdem werden Benutzer und Zeitpunkt jeder fachlich relevanten Aktion protokolliert.

## 7. Fachliches Datenmodell

Die Feldangaben sind Zielvorgaben; genaue Django-Optionen werden in den Models und Migrationen festgelegt.

### 7.1 Mandant und Bankkonto

```text
Mandant
  id
  name                         # Immo-Fuchs KG
  kurzname
  steuerliche_id, blank
  waehrung                     # EUR
  aktiv

Bankkonto
  id
  mandant -> Mandant
  iban_normalisiert
  bezeichnung
  waehrung
  aktiv_von / aktiv_bis
  unique(mandant, iban_normalisiert)
```

Alle fachlichen Objekte werden einem Mandanten zugeordnet. Daten verschiedener Rechtsträger dürfen nicht im selben Export vermischt werden. Nicht zur Immo-Fuchs KG gehörende Liegenschaften werden im MVP nicht aufgenommen.

### 7.2 Import

```text
ImportVorgang
  id
  mandant -> Mandant
  bankkonto -> Bankkonto
  quelle                       # JSON / OFX
  original_dateiname
  datei_sha256
  parser_version
  zeitraum_von / zeitraum_bis
  anzahl_gelesen
  anzahl_neu
  anzahl_duplikate
  anzahl_fehler
  status                       # hochgeladen, validiert, importiert, fehlgeschlagen
  importiert_von
  importiert_am
  fehlerprotokoll

BankTransaktion
  id
  mandant -> Mandant
  bankkonto -> Bankkonto
  import_vorgang -> ImportVorgang
  quelle
  quellen_referenz             # JSON referenceNumber / OFX FITID
  fingerprint
  buchungsdatum
  valutadatum, null
  betrag                       # DecimalField, bereits in EUR umgerechnet
  waehrung
  partner_name
  partner_iban_normalisiert, blank
  verwendungszweck, blank
  rohdatensatz                 # JSONField für nachvollziehbaren Import
  status                       # offen, vollständig_zugeordnet, ignoriert
  ignoriert_grund, blank
  unique(bankkonto, quelle, quellen_referenz)
  unique(bankkonto, fingerprint)
```

Der Fingerprint wird aus stabilen normalisierten Werten gebildet, beispielsweise Konto, Buchungsdatum, Betrag, Partner-IBAN, Partnername und Referenztext. Er schützt zusätzlich vor einem Doppelimport derselben Bewegung aus JSON und OFX.

### 7.3 Kontenplan und Kostenstellen

```text
KontenplanVersion
  id
  mandant -> Mandant
  bezeichnung
  gueltig_ab
  vorlage_dateiname
  vorlage_sha256
  importiert_am
  aktiv

KontenplanEintrag
  id
  version -> KontenplanVersion
  kategorie_text               # exakter Wert aus Kontenplan!D
  kontonummer                  # CharField, um führende Nullen zu erhalten
  bezeichnung
  kontoart                     # CharField
  kontoklasse                  # CharField
  ust_stcode, blank
  ust_prozent, null
  aktiv
  unique(version, kategorie_text)

Kostenstelle
  id
  mandant -> Mandant
  code                         # z.B. BHG14
  bezeichnung
  external_source, blank
  external_id, blank
  aktiv_von / aktiv_bis
  unique(mandant, code)
```

Eine Kostenstelle ist eine Buchhaltungsdimension und keine Liegenschaft im Sinne der Hausverwaltung.

### 7.4 Geschäftspartner und Hausverwaltungsprojektion

```text
Geschaeftspartner
  id
  mandant -> Mandant
  name
  iban_normalisiert, blank
  typ                          # kunde, lieferant, sonstiger
  aktiv

ExternesMatchingProfil
  id
  mandant -> Mandant
  source_system                # quintus_property_management
  external_id                  # stabile Mietverhältnis-ID
  anzeigename
  iban_normalisiert
  kostenstelle_code
  gueltig_von / gueltig_bis
  erwarteter_gesamtbetrag, null
  erwartete_bestandteile       # JSONField: HMZ/BK/Heizung/Parkplatz
  fetched_at
  source_updated_at, null
  aktiv
  unique(source_system, external_id, iban_normalisiert, gueltig_von)
```

`ExternesMatchingProfil` ist ein nicht manuell bearbeitbarer Matching-Cache. Es ersetzt keine Person und kein Mietverhältnis.

### 7.5 Buchung und Buchungszeilen

```text
Buchung
  id
  mandant -> Mandant
  bank_transaktion -> BankTransaktion, null
  belegkreis                   # BK / KA / PR
  zahlungsdatum
  belegnummer                  # standardmäßig Monatsnummer, explizit gespeichert
  status                       # entwurf, zu_pruefen, geprueft, freigegeben,
                               # exportiert, storniert
  matching_confidence, null
  matching_begruendung, blank
  matching_snapshot, blank     # verwendete externe Daten zum Zeitpunkt des Matchings
  erstellt_von / erstellt_am
  geprueft_von / geprueft_am, null
  freigegeben_von / freigegeben_am, null
  exportiert_am, null
  version                      # Optimistic Locking

Buchungszeile
  id
  buchung -> Buchung
  positionsnummer
  text
  rechnungsnummer, blank
  lieferant_kunde
  geschaeftspartner -> Geschaeftspartner, null
  betrag_brutto
  ust_symbol                   # 0, 10, 13, 20, IG, RC
  kategorie -> KontenplanEintrag
  kostenstelle -> Kostenstelle, null
  notiz, blank
  unique(buchung, positionsnummer)
```

Für eine BK-Buchung gilt:

```text
Summe(Buchungszeile.betrag_brutto) = BankTransaktion.betrag
```

Die Buchung kann erst freigegeben werden, wenn die Differenz 0,00 EUR beträgt. Dadurch können Mietzahlungen oder Sammelzahlungen auf mehrere Kategorien und USt-Sätze aufgeteilt werden.

### 7.6 Belege und Paperless

```text
Beleg
  id
  mandant -> Mandant
  paperless_document_id, null
  original_dateiname
  datei_sha256
  dokumenttyp                  # einzelbeleg, kontoauszug_pdf, sonstig
  dokumentdatum, null
  betrag_brutto, null
  sync_status                  # lokal, upload_laeuft, synchronisiert, fehler
  sync_fehler, blank
  hochgeladen_von / hochgeladen_am
  unique(mandant, datei_sha256)

BelegZuordnung
  id
  beleg -> Beleg
  buchung -> Buchung
  rolle                        # hauptbeleg, zusatzbeleg, kontoauszug
  unique(beleg, buchung, rolle)
```

Eine Buchung kann mehrere Belege und ein Beleg mehrere Buchungen haben. Der Paperless-Status ist nicht die fachliche Wahrheit über die Buchungsfreigabe; Bookkeeping bleibt dafür führend.

### 7.7 Regeln und Audit

```text
MatchingRegel
  id
  mandant -> Mandant
  bankkonto -> Bankkonto, null
  regeltyp                     # iban, text_enthaelt, exakter_text, betrag, kombiniert
  bedingungen                  # strukturierte JSON-Bedingungen
  ziel_belegkreis
  ziel_kategorie -> KontenplanEintrag, null
  ziel_kostenstelle -> Kostenstelle, null
  ziel_ust_symbol, blank
  prioritaet
  gueltig_von / gueltig_bis
  aktiv
  erstellt_von / erstellt_am

AuditEreignis
  id
  mandant -> Mandant
  objekt_typ
  objekt_id
  aktion
  vorher, blank
  nachher, blank
  benutzer
  zeitpunkt
  correlation_id
```

Jeder Vorschlag zeigt die angewendete Regel, die Match-Gründe und das Vertrauen an. Regeln dürfen Vorschläge erzeugen, aber keine Buchungen automatisch freigeben.

### 7.8 Export

```text
ExportVorgang
  id
  mandant -> Mandant
  kontenplan_version -> KontenplanVersion
  zeitraum_von / zeitraum_bis
  quartal
  bank_anfangssaldo
  kassa_anfangssaldo
  status                       # entwurf, validiert, erstellt, abgeschlossen, verworfen
  vorlage_sha256
  export_datei_sha256, null
  belege_manifest_sha256, null
  erstellt_von / erstellt_am
  abgeschlossen_von / abgeschlossen_am, null

ExportBuchung
  export_vorgang -> ExportVorgang
  buchung -> Buchung
  excel_startzeile
  excel_zeilenanzahl
  unique(export_vorgang, buchung)
```

Ein abgeschlossener Export ist unveränderlich. Eine nachträgliche Korrektur erfolgt durch Storno/Korrekturbuchung und einen neuen Exportvorgang, nicht durch Überschreiben der Historie.

## 8. Workflows

### 8.1 Bankimport

1. Benutzer wählt Mandant und Bankkonto.
2. JSON/OFX wird hochgeladen und gehasht.
3. Parser validiert Struktur, Währung, Datum und Betragspräzision.
4. Duplikate werden über Quellreferenz und Fingerprint erkannt.
5. Importergebnis wird vor endgültigem Import angezeigt.
6. Neue Transaktionen erhalten Status `offen`.
7. Jede Transaktion muss gebucht oder mit Begründung ignoriert werden.

### 8.2 Matching

Reihenfolge:

1. exakte manuelle Matching-Regel
2. Partner-IBAN gegen Geschäftspartner
3. Partner-IBAN gegen aktives externes Matchingprofil
4. Betrag und Gültigkeitszeitraum gegen erwartete Mietzahlung
5. Textregeln
6. historische, bereits freigegebene Buchungen
7. optionaler KI-Vorschlag für unbekannte Fälle

IBAN allein reicht nicht für eine automatische fachliche Entscheidung. Bei mehreren passenden Profilen, abweichendem Betrag oder abgelaufenem Mietverhältnis wird zwingend manuell geprüft.

### 8.3 Belegworkflow

- Vorhandenen Beleg in Paperless suchen oder neuen Beleg hochladen.
- Paperless-Verarbeitung kann asynchron sein; Bookkeeping zeigt den Sync-Status.
- Betrag, Dokumentdatum, Lieferant und Rechnungsnummer werden als Prüfhinweise angezeigt.
- Abweichungen blockieren nicht automatisch, verlangen aber eine Begründung.
- Daueraufträge können ausdrücklich als „kein Einzelbeleg erforderlich“ konfiguriert werden.

### 8.4 Freigabe

Vor Freigabe müssen gelten:

- Buchung ist vollständig einer Kategorie zugeordnet.
- Summe der Zeilen stimmt bei BK exakt mit der Banktransaktion überein.
- USt-Symbol ist zulässig.
- Kategorie existiert in der aktiven Kontenplanversion.
- Pflichtbeleg ist zugeordnet oder eine dokumentierte Ausnahme liegt vor.
- Sonderfälle `IG` und `RC` sind manuell bestätigt.
- Mandant ist eindeutig.

### 8.5 Quartalsexport

1. Zeitraum und Kontenplanversion wählen.
2. Anfangssalden Bank/Kassa erfassen und bestätigen.
3. Nur freigegebene, noch nicht exportierte Buchungen auswählen.
4. Vorprüfung auf fehlende Belege, offene Bankbewegungen und Zeilenlimit.
5. Kopie der Originalvorlage erstellen.
6. A–H und K schreiben; eine Buchungszeile entspricht einer Excel-Zeile.
7. Formeln neu berechnen lassen.
8. Summen, Bankkontrolle, Kassa und Anzahl der Zeilen abgleichen.
9. Belege und Kontoauszüge sammeln; Manifest mit Buchungs-ID, Dateiname und Hash erzeugen.
10. Benutzer prüft und schließt den Export ab.

## 9. USt- und Buchungslogik

- USt und Kategorie werden vorgeschlagen, aber immer explizit freigegeben.
- Wohnraumvermietung, Parkplätze, Heizkosten, steuerfreie Vorgänge, IG und RC werden nicht allein über den Objektnamen entschieden.
- Eine Zahlung kann auf Zeilen mit unterschiedlichen USt-Sätzen aufgeteilt werden.
- Kontenplanwerte sind vorlagenabhängig und werden versioniert.
- Aktivierungspflichtige Anschaffungen und AfA werden nicht als gewöhnliche sofortige Ausgabe automatisiert; sie werden markiert und dem Steuerberater zur Prüfung vorgelegt.
- Die fachlichen Regeln werden vor produktiver Nutzung anhand repräsentativer Fälle vom Steuerberater bestätigt.

## 10. Unveränderbarkeit, Aufbewahrung und Sicherheit

- Freigegebene Buchungen werden nicht still geändert; Änderungen erzeugen Auditereignisse und erneute Prüfung.
- Exportierte Buchungen sind gesperrt.
- Originalimporte und Belege werden mit SHA-256-Prüfsumme gespeichert.
- API-Token und Datenbankpasswörter liegen ausschließlich in geschützter Konfiguration/Umgebungsvariablen.
- Paperless-Zugriff erfolgt über ein eigenes Konto/Token mit minimal erforderlichen Rechten.
- Regelmäßige Backups umfassen Datenbank, Exportdateien, Konfiguration und notwendige Zuordnungsdaten.
- Restore-Tests sind Teil des Betriebs.
- Allgemeine Buchhaltungsunterlagen werden entsprechend den österreichischen Fristen aufbewahrt; für bestimmte grundstücksbezogene USt-Unterlagen können längere Fristen gelten.

## 11. KI-Unterstützung

KI ist frühestens nach einer stabilen regelbasierten Version vorgesehen.

Zulässig:

- Kategorie-Vorschlag aus Buchungstext oder OCR-Text
- Vorschlag eines Geschäftspartners
- Erkennen ungewöhnlicher Abweichungen

Nicht zulässig:

- automatische Freigabe
- eigenständige Steuerentscheidung
- Änderung historischer Buchungen
- unprotokollierte Übermittlung vollständiger Dokumente oder unnötiger personenbezogener Daten

Jeder KI-Vorschlag speichert Modell, Zeitpunkt, Eingabekategorie, Ergebnis und Konfidenz. Personenbezogene Daten werden minimiert.

## 12. Tests und Abnahmekriterien

### 12.1 Import

- `amount.value` wird unter Berücksichtigung von `precision` korrekt umgerechnet.
- Positives und negatives Vorzeichen bleiben erhalten.
- JSON-Datumswerte mit Zeitzone werden korrekt als lokales Datum übernommen.
- Doppelimport derselben Datei erzeugt keine neuen Transaktionen.
- JSON und OFX derselben Bewegung erzeugen keine Doppelbuchung.
- Fehlende oder doppelte Referenzen führen zu nachvollziehbarer Behandlung.

### 12.2 Matching

- bekannte Mieter-IBAN liefert das richtige aktive Profil und die Kostenstelle.
- abgelaufenes Mietverhältnis wird nicht ohne Warnung verwendet.
- gemeinsames Konto oder mehrere Treffer erzwingen manuelle Auswahl.
- abweichender Mietbetrag wird markiert.
- Parkplatz- und Wohnungsbestandteile können unterschiedliche USt-Sätze erhalten.

### 12.3 Buchung

- Split-Buchung muss exakt auf den Bankbetrag summieren.
- negative und positive Buchungen werden korrekt exportiert.
- Buchung ohne gültige Kategorie kann nicht freigegeben werden.
- exportierte Buchung ist gesperrt.
- Storno und Korrektur bleiben vollständig nachvollziehbar.

### 12.4 Excel

- A–H und K werden korrekt geschrieben.
- B enthält die erwartete Belegnummer/Monatsnummer.
- I, J und L–S behalten ihre Formeln.
- `CSV`, `Auswertung` und `UVA` bleiben funktionsfähig.
- Anfangssalden und Kontrollsummen sind nachvollziehbar.
- Kontonummer, Gegenkonto, USt- und VSt-Kennzeichen entsprechen der Vorlage.
- Export gegen das vorhandene Q2-Beispiel wird zeilen- und summenweise verglichen.

### 12.5 Systemgrenze

- Bookkeeping startet und funktioniert ohne `bookkeeping_property_bridge`.
- In `bookkeeping` existiert kein Import von Hausverwaltungsmodels.
- Änderung eines Mieters verändert keine freigegebene historische Buchung.
- Bridge überträgt keine unnötigen personenbezogenen Felder.
- Bookkeeping verwendet ein eigenes Basis-Template und eine eigene Navigation.
- Bookkeeping-Seiten funktionieren ohne Templates, CSS oder JavaScript aus `webapp`.
- Benutzer ohne Bookkeeping-Berechtigung können den Arbeitsbereich nicht öffnen.
- Das Hausverwaltungs-Dashboard und dessen Navigation werden durch Bookkeeping nicht verändert.

## 13. Phasenplan

### Phase 0 – Entscheidungen und technische Vorbereitung

- Quintus-Repository und aktuelle Apps prüfen.
- Mandantenumfang mit Steuerberater bestätigen.
- Festlegen, welche Objekte tatsächlich zur Immo-Fuchs KG gehören.
- Bedeutung des `CSV`-Sheets und der Spalte B bestätigen.
- Anfangssaldo-/Kontrollsummenprozess klären.
- PostgreSQL-Migrationszeitpunkt entscheiden.

### Phase 1 – Fundament

- Django-App `bookkeeping` anlegen.
- Rollen, Mandant, Bankkonto, Kontenplanversion, Kostenstellen und Auditbasis implementieren.
- Steuerberater-Vorlage importieren und versionieren.
- eigenen URL-Namespace, Login-Einstieg, Basis-Template und Bookkeeping-Navigation erstellen.
- Dashboard-Grundgerüst mit ausschließlich buchhaltungsbezogenen Kennzahlen erstellen.

### Phase 2 – Bankimport

- JSON-Parser anhand der vorliegenden Datei implementieren.
- OFX-Fallback ergänzen.
- Importvorgang, Hash, Referenz und Fingerprint testen.
- Import-Review-UI erstellen.

### Phase 3 – Buchung und Matching v1

- Buchung/Buchungszeilen und Split-Validierung implementieren.
- Geschäftspartner und manuelle Regeln ergänzen.
- dedizierten Review-Arbeitsplatz und Freigabeoberfläche erstellen.

### Phase 4 – Hausverwaltungs-Bridge

- minimale Matching-Projektion definieren.
- `bookkeeping_property_bridge` implementieren.
- Sync, Gültigkeit, Konflikte und Snapshots testen.

Diese Phase kann entfallen, wenn manuelle Partner- und IBAN-Regeln für das Volumen ausreichen.

### Phase 5 – Paperless

- Suche, Upload, Statusabfrage und Belegzuordnung implementieren.
- Hash-, Retry- und Fehlerfälle testen.
- Kontoauszugs-PDF als Quartalsdokument behandeln.

### Phase 6 – Excel und Quartalspaket

- versionierten Export implementieren.
- Formel- und Summenprüfung automatisieren.
- Belegmanifest und Paket erstellen.
- Abnahme mit Q2-Beispieldaten durchführen.

### Phase 7 – Betrieb und Optimierung

- Backup/Restore testen.
- wiederkehrende Regeln anhand freigegebener Buchungen verbessern.
- erst bei Bedarf PostgreSQL, Hintergrundjobs und KI-Unterstützung ergänzen.

## 14. Offene Entscheidungen

1. Welche Liegenschaften und Bankkonten gehören steuerlich tatsächlich zur Immo-Fuchs KG?
2. Geht das `CSV`-Sheet zusätzlich zum Excel an den Steuerberater?
3. Ist Spalte B immer die Monatsnummer oder gibt es eine andere Belegnummernlogik?
4. Welcher Anfangssaldo wird für ein Quartal in `G2` erwartet und wie wird er belegt?
5. Welche Daueraufträge benötigen laut Steuerberater keinen Einzelbeleg?
6. Welche Kategorien/USt-Aufteilungen gelten für HMZ, BK, Heizung und Parkplätze?
7. Soll die Hausverwaltungs-Bridge bereits im MVP enthalten sein oder erst nach einem manuellen Matching-Test?
8. Erfolgt die PostgreSQL-Migration vor Phase 1 oder nach dem Einbenutzer-MVP?

## 15. Empfehlung zum Start

Zuerst wird Bookkeeping **ohne Hausverwaltungsabhängigkeit** bis zu einem funktionierenden Bankimport und manuellen Matching gebaut. Danach wird anhand der tatsächlich offenen Transaktionen gemessen, welchen Nutzen die Hausverwaltungs-Bridge bringt.

Wenn Mieterzahlungen einen wesentlichen Anteil der manuellen Zuordnung ausmachen, wird die Bridge ergänzt. Sie liefert dann nur IBAN, Gültigkeitszeitraum, erwartete Zahlung und Kostenstellencode. Die Hausverwaltung bleibt Quelle der Wahrheit; Bookkeeping speichert lediglich den für den Buchungsvorschlag verwendeten Snapshot.

## 16. Quellen und Arbeitsgrundlagen

- `EinnahmenAusgabenRechnung Immo-Fuchs KG 2026 Q2.xlsx`, bereitgestellt am 03.08.2026
- `AT822011184722039000_2026-07-01_2026-07-31.json`, bereitgestellt am 03.08.2026
- Österreichisches Unternehmensserviceportal, Einnahmen-Ausgaben-Rechnung: https://www.usp.gv.at/themen/steuern-finanzen/steuerliche-gewinnermittlung/einnahmen-ausgaben-rechnung.html
- Österreichisches Unternehmensserviceportal, Aufbewahrungspflicht: https://www.usp.gv.at/themen/steuern-finanzen/steuerliche-gewinnermittlung/weitere-informationen-zur-steuerlichen-gewinnermittlung/betriebliches-rechnungswesen/aufbewahrungspflicht.html
- Bundesministerium für Finanzen, Vermietung und Verpachtung in der Umsatzsteuer: https://www.bmf.gv.at/themen/steuern/immobilien-grundstuecke/vermietung-verpachtung/vermietung-und-verpachtung-in-der-umsatzsteuer.html
- Bundesministerium für Finanzen, Vorsteuerberichtigungszeitraum bei Grundstücken: https://www.bmf.gv.at/themen/steuern/fuer-unternehmen/umsatzsteuer/informationen/vorsteuerberichtigungszeitraum_bei_Grundst%C3%BCcken.html
