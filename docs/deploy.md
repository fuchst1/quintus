# Deployment Hinweise

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

- `BK_PORTAL_BASE_URL` (z. B. `https://belege.example.at/export`)
- `BK_PORTAL_TOKEN_SECRET` (eigener geheimer Schlüssel, nicht öffentlich)
- `BK_PORTAL_PATH_PREFIX` (Default `m`)

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
