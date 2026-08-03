# Deployment Hinweise

## Bookkeeping

Die Bookkeeping-App läuft in derselben Quintus-Installation, Virtualenv und
Gunicorn/systemd-Instanz wie die Hausverwaltung. Es wird kein separater Server
und keine zusätzliche Datenbank betrieben.

`requirements.txt` enthält `openpyxl` für den Import der versionierten
Steuerberater-Vorlagen. Nach einem regulären Deployment müssen die
Abhängigkeiten wie bisher in der bestehenden Virtualenv installiert werden.

Die hochgeladenen Kontenplanvorlagen liegen geschützt unter
`media/bookkeeping/`. Dieses Verzeichnis ist zusammen mit Datenbank,
Konfiguration und Exportdateien in die bestehenden Backups aufzunehmen. Django
liefert Medien im Debug-Betrieb nicht direkt aus; Bookkeeping-Vorlagen werden
in Phase 1 nicht als öffentliche Dateien angeboten.

## PDF-Erzeugung für BK-Briefe (WeasyPrint)

Die BK-Mieterbriefe verwenden WeasyPrint für die PDF-Ausgabe.

### Python-Abhängigkeit

`requirements.txt` enthält:

- `weasyprint==62.3`

### Systempakete (Debian 13)

Für WeasyPrint werden native Bibliotheken benötigt. Beispiel:

```bash
sudo apt update
sudo apt install -y \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libcairo2 \
  libgdk-pixbuf-2.0-0 \
  libffi8 \
  shared-mime-info
```

Hinweis: Falls in der Zielumgebung zusätzliche Schrift-/Renderingpakete fehlen, fällt das System automatisch auf den Legacy-PDF-Fallback zurück.

### Verhalten bei fehlender WeasyPrint-Runtime

Wenn WeasyPrint nicht importiert werden kann oder bei der Laufzeit-Konvertierung fehlschlägt, verwendet das System automatisch den bestehenden Legacy-PDF-Fallback, damit der Brief-Download weiterhin funktioniert.

## Erinnerungen (E-Mail + UI)

### Erforderliche Umgebungsvariablen

Standard ist direkter SMTP-Versand aus Django (kein lokaler Postfix erforderlich).

Beispielwerte in `.env.example`:

- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `EMAIL_USE_SSL`
- `DEFAULT_FROM_EMAIL`

### Geplanter Versand per Cron

Wöchentlicher Versand Montag 08:00 (Server-Zeitzone: `Europe/Vienna`):

```bash
0 8 * * 1 cd /home/quintus/apps/quintus && . .venv/bin/activate && python manage.py send_reminders >> logs/send_reminders.log 2>&1
```

Optionaler Testlauf ohne Versand:

```bash
python manage.py send_reminders --dry-run
```

## Monatliche Mietkonto-SOLL-Buchungen

### Voraussetzung

Einmalig das Log-Verzeichnis anlegen, damit Cron-Ausgaben in `logs/*.log`
geschrieben werden koennen:

```bash
mkdir -p /home/quintus/apps/quintus/logs
```

### Geplanter Monatslauf per Cron

Monatlicher Lauf am 1. des Monats um 08:00
(Server-Zeitzone: `Europe/Vienna`):

```bash
0 8 1 * * cd /home/quintus/apps/quintus && . .venv/bin/activate && python manage.py generate_monthly_soll >> logs/generate_monthly_soll.log 2>&1
```

Der kanonische Command fuer diesen Lauf ist `generate_monthly_soll`.
Das Alias `generate_rent_debits` bleibt nur aus Kompatibilitaetsgruenden erhalten.

### Manueller Nachhol-Lauf bei Ausfall

Wenn der Monatslauf ausfaellt, werden fehlende Monate gezielt manuell nachgezogen:

```bash
python manage.py generate_monthly_soll --month 2026-01
python manage.py generate_monthly_soll --month 2026-02
python manage.py generate_monthly_soll --month 2026-03
```

Hinweis zum aktuellen Stand vom `2026-03-19`:
Fuer `2026-01-01`, `2026-02-01` und `2026-03-01` fehlen derzeit die regulaeren
Monats-SOLL-Buchungen. Mit den aktuell 10 aktiven Mietvertraegen sind fuer jeden
dieser Monate derzeit 21 erzeugbare SOLL-Buchungen zu erwarten.

## VPI-Jahresprozess (VPI 2020)

### Operativer Ablauf

1. **Indexwert pflegen und freigeben**
   In der App unter `Verwaltung -> VPI-Anpassung` den neuen Monatswert erfassen:
   - `Monat` immer als 1. des Monats (z. B. `2026-02-01`)
   - `VPI 2020` eintragen
   - `Veröffentlicht` aktivieren (optional `Veröffentlicht am`)

2. **Lauf öffnen**
   Für den freigegebenen Indexmonat den Lauf starten (`Lauf öffnen`).

3. **Vorschau prüfen und Briefe erzeugen**
   Im Lauf:
   - Startnummer setzen
   - optionalen Freitext speichern
   - `Briefe erzeugen (ZIP + Ablage)` ausführen  
   Dabei werden PDFs erzeugt und beim jeweiligen Mietvertrag abgelegt.

4. **Anpassung anwenden**
   Erst danach `Anpassung anwenden` ausführen.  
   Das System aktualisiert je betroffenem VPI-Vertrag:
   - `HMZ Netto`
   - `Index-Basiswert`
   - `Letzte Wertsicherung`  
   und erstellt bei positiver Rückwirkung eine Sammel-SOLL-Buchung (`HMZ`) für die Nachverrechnung.

### Optionaler Cron: freigegebene Indexwerte ohne Lauf prüfen

```bash
15 8 1 * * cd /home/quintus/apps/quintus && . .venv/bin/activate && python manage.py check_vpi_releases >> logs/check_vpi_releases.log 2>&1
```

Optional mit automatischer Draft-Lauf-Erzeugung:

```bash
python manage.py check_vpi_releases --create-runs
```

## BK-Mieterportal (statischer Export + QR)

### Umgebungsvariablen

Für QR-Link und Portal-Export:

- `BK_PORTAL_BASE_URL` (z. B. `https://belege.example.at/belege`)
- `BK_PORTAL_PATH_PREFIX` (optional, z. B. `BHG14`; sonst Ableitung aus Liegenschaftsname)
- `BK_PORTAL_TOKEN_SECRET` (eigener geheimer Schlüssel, nicht öffentlich)

Portal-Pfad wird automatisch erzeugt als:

- `<BK_PORTAL_BASE_URL>/<Liegenschaft>/<Jahr>/<Token>/`
- Beispiel: `https://belege.example.at/belege/BHG14/2026/abc123token.../`

### Export ausführen

Im BK-Lauf:
- Button `Portal-Export (ZIP)` erzeugt ein vollständiges statisches Paket.

Per CLI:

```bash
python manage.py export_bk_portal --run-id 12 --output /home/quintus/exports/bk-portal.zip
```

Alternativ per Liegenschaft/Jahr:

```bash
python manage.py export_bk_portal --liegenschaft-id 3 --jahr 2025
```

### Webserver-Härtung für statisches Hosting

- Directory Listing deaktivieren.
- Indexierung deaktivieren (`robots.txt` + `X-Robots-Tag: noindex, nofollow`).
- Token-URLs als geheim behandeln (nicht verlinken/teilen außerhalb der Briefe).
- Bei vermutetem Leak: Export neu erzeugen und alte Exportdateien entfernen.

## Paperless-ngx (Testsuche)

### Umgebungsvariablen

Für die Testseite `Einstellungen -> Paperless DMS (Test)`:

- `PAPERLESS_BASE_URL` (z. B. `https://paperless.example.at`)
- `PAPERLESS_API_TOKEN` (API-Token eines Paperless-Benutzers mit Leserechten)
- `PAPERLESS_TIMEOUT_SECONDS` (Timeout der Suchanfrage in Sekunden, Standard `10`)
- `PAPERLESS_LEASE_DOCUMENT_TYPE_ID` (optional, Dokumenttyp-ID für Mietverträge; wenn leer, versucht Quintus den Typnamen `Mietvertrag` in Paperless aufzulösen)
- `PAPERLESS_BK_DOCUMENT_TYPE_ID` (optional, Dokumenttyp-ID für Betriebskostenbelege; wenn leer, versucht Quintus den Typnamen `Rechnung` in Paperless aufzulösen)
- `PAPERLESS_METER_READING_DOCUMENT_TYPE_ID` (optional, Dokumenttyp-ID für Zählerstand-Bilder, Standard `6`)

Hinweis:
`PAPERLESS_BASE_URL` kann mit oder ohne `/api` angegeben werden
(z. B. `http://paperless-ifkg:8000` oder `http://paperless-ifkg:8000/api`).

### Verhalten bei fehlender Konfiguration

Wenn `PAPERLESS_BASE_URL` oder `PAPERLESS_API_TOKEN` fehlt, bleibt Quintus lauffähig.
Die Testseite zeigt dann nur einen Hinweis zur fehlenden Konfiguration, ohne Serverfehler.

### Erweiterte Filter in der Testsuche

Die Testsuche unterstützt zusätzlich:

- `q_liegenschaft` (z. B. `BHG14`)
- `q_einheit` (z. B. `BHG14_1`)

Diese werden als `custom_field_query` an Paperless übergeben.

Anzeige-Hinweis:
Wenn Paperless für diese Felder interne Options-IDs speichert, löst Quintus die IDs
über die `custom_fields`-Definitionen auf und zeigt die lesbaren Labels an.
