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
