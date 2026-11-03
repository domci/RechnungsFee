# Sicherheitsprüfung: RechnungsFee / Docker-Overlay

Stand: 24.10.2026, Task `t_62f5c12b`, Fortsetzung von PR #1.
**Nicht freigegeben, nicht veröffentlicht, nicht auf Bestandsdaten gestartet.**

## Änderungen und Prüfeinheiten

- Python: `Pillow==12.3.0` → `13.0.0`. `requirements-dev.txt` inkludiert die Produktionsanforderungen; PyYAML für den Workflow-Regressionstest explizit deklariert.
- Frontend: bisherige Router/Vite-/Transitivkorrekturen aus PR #1 beibehalten; Zod auf 4.6.7 im npm-Lock aktualisiert.
- Cargo: rustls 0.23.46, rustls-webpki 0.103.16, webpki-root-certs 1.0.10 und Tokio 1.54.1. Nicht nur die zwei GitHub-Alerts, sondern die aktuelle RustSec-Datenbank geprüft.
- CI prüft beide Python-Einstiegspunkte, npm-Audit/Build sowie Linux-Tauri-Build und Cargo-Audit inklusive `--deny unsound`.
- Release-Workflow ruft dieselbe CI auf. Build/Updater/Veröffentlichung laufen nur bei erfolgreichen Voraussetzungen; die bisherigen `!cancelled()`-Overrides konnten nach fehlgeschlagenen Builds veröffentlichen.
- PyInstaller verwendet pro Build ein eigenes temporäres Verzeichnis unter `TMPDIR` statt globaler, kollidierender `/tmp`-Pfade.

| Einheit | Vorher | Kandidat |
|---|---:|---:|
| GitHub offene Alerts auf **main**, alle vier Manifeste | 100 (41+41 Python, 16 npm, 2 Cargo) | unverändert, solange PR nicht gemergt |
| pip-audit Produktionsauflösung, Python 3.12 | 37 Befunde, Pillow | 0 |
| pip-audit Entwicklungsauflösung, Python 3.12 | Produktionsanforderungen inkludiert | 0 |
| npm-Audit, PR-Lock bei Übernahme | 1 betroffenes Paket, Zod | 0 |
| cargo-audit, gesamtes plattformübergreifendes Lock | 9 Schwachstellen plus Unsoundness-/Unmaintained-Warnungen | 3 zip-Schwachstellen plus glib-Unsoundness; Unmaintained-Warnungen bleiben |
| pip-audit **installierte Pakete** im ausgewählten v0.6.4-Basisimage | 49 | unverändert |
| pip-audit **installierte Pakete** im tatsächlich laufenden Overlay | 49 | unverändert |

Zählungen sind nicht austauschbar: GitHub zählt Advisory/Manifest, npm betroffene Pakete, pip-audit/Cargo zählen Advisory/Paket. Ein sauberer neu aufgelöster Host-Graph beweist kein sauberes vorhandenes Image. Python-Anforderungen enthalten weiterhin unversionierte transitive Auflösungen; sie sind kein vollständiger reproduzierbarer Lock.

## Verifiziert

- Backend: vollständige Testsuite grün. Der zuvor kalendertagsabhängige Gutschrift-Test wird nun explizit vor und ab dem Vorsteuer-Cutover geprüft, einschließlich HTTP-Fehler/Rollback und ausbleibender Journalbuchung. Keine Finanzlogik geändert.
- Frontend: `npm ci`, `npm audit`, `tsc -b && vite build` erfolgreich. Lint unverändert bei 119 Fehlern / 13 Warnungen; keine Abschwächung oder Unterdrückung.
- PyInstaller-Sidecar erfolgreich gebaut.
- Linux-Tauri-Release-Binary mit echtem Tauri-CLI gebaut, ohne Installer/Signierung/Veröffentlichung. Vorab gebautes Frontend wiederverwendet.
- Desktop in einem separaten Docker-Container ohne Netzwerk und ohne Produktionsmounts unter Xvfb gestartet. Webview ruft `/api/setup/status` auf; gebündeltes Sidecar liefert `/health` sowie Kategorien/Konten/Kunden/Lieferanten jeweils HTTP 200. Frisches synthetisches HOME. Das ist Startup-/API-Smoke, keine vollständige visuelle oder Windows/macOS-Akzeptanz.
- Lokale Workflow-Prüfung mit actionlint; Regressionstest sichert die Release-Abhängigkeitskette.

## Nicht aufgelöste Release-Blocker

1. `glib 0.18.5`, RUSTSEC-2024-0429: GTK3/WebKit/Tauri erfordern weiterhin die inkompatible ältere Reihe. Die aktuelle stabile Tauri-Version 2.12.5 verlangt GTK `^0.18`, WebKit 2.0.2 ebenfalls glib `^0.18.0`; glib 0.20 ist kein einfacher Lockfile-Austausch.
2. `zip 4.6.1`: RUSTSEC-2026-0367/0368/0369, Fix ab 9.0.0. Über `tauri-plugin-updater` im Windows-Graph. Auch aktueller Updater 2.14.0 verlangt `zip ^4`; kein kompatibles Lockfile-Update. Kein Ignore, keine Alert-Dismissals, kein Entfernen des Updaters zur Scannerkosmetik.
3. Das Fork hat keine eigenen Release-/Signing-Secrets; der Desktop-Updater zeigt auf den öffentlichen Upstream samt dessen Public Key. Eigene Release-Vertrauens-/Updater-Strategie ist vor einer Fork-Veröffentlichung zu entscheiden. Kein Schlüssel erzeugt oder ersetzt.
4. Das Docker-Overlay bezieht standardmäßig **nicolettas-muggelbude/RechnungsFee**, nicht diesen Fork. Ein Fork-Merge aktualisiert diese Images nicht.
5. Tatsächlich läuft `local-incomplete160-0d7cff51`, auf v0.6.4 / `38cfc5da3fedfa466ac6406246bf9fcb89f403c3` aufgebaut, mit zusätzlichen lokalen Änderungen und Schema **160**. PR-Quellcode hat Schema **159**. Ein Austausch würde lokale Funktionalität verlieren und kann durch Startup-Datenfixes Finanzdaten verändern. Keine Freigabe für einen solchen Austausch aus einer reinen Dependency-Aktualisierung ableiten.
6. Beide vorhandenen Backend-Images enthalten Pillow 12.3.0 (37), pypdf 6.19.0 (11), certifi 2026.7.22 (1): insgesamt 49 pip-audit-Befunde. Kein Kandidaten-Release-Image behauptet, solange kein freigegebenes Release existiert.

Exakte PR-Head-/CI-IDs, Roh-Audits, Build-/Runtime-Logs und Image-IDs liegen im angehängten Kanban-Evidenzpaket. Der Fork-Workflow war bei Übernahme über die Actions-API nicht registriert (404), obwohl Actions-Berechtigungen aktiviert waren. Fehlende/rote Exact-Head-CI ist kein grüner Status.

## Nächster zulässiger Schritt

Erst die Tauri-Upstream-/gepflegte-Backport-Strategie für glib und zip festlegen und prüfen, dann Exact-Head-CI grün bekommen. Separat Fork-Signierung/Updater und Erhalt des lokalen Schema-160-Overlays entscheiden. Danach einen exakt gepinnten Release-Kandidaten ohne Bestandsdaten bauen und Desktop-/Backend-Akzeptanz durchführen. Keine automatische Aktualisierung des laufenden Dienstes, kein Image-Rollback gegen bereits migrierte Datenbanken.
