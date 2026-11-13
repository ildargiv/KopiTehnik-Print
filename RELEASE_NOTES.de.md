[English](RELEASE_NOTES.md) | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | **Deutsch** | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Versionshinweise — v1.9.0

- **Eingebauter KI-Agent „Print Assistant“ (Beta, standardmäßig ausgeschaltet)**: Agent-Reiter im rechten Bereich und zweizeilige Eingabe unter den Reitern (in jedem Reiter nutzbar), Schnelltasten Improve, Crop, Prepare, Print. Getippter Ordner plus Taste ist ein Befehl; mehrere Tasten laufen der Reihe nach. Es wird nichts gesendet, bevor der Agent eingeschaltet und eine Modelladresse angegeben ist.
- **Beliebiges OpenAI-kompatibles Modell**: lokales llama.cpp, Ollama, vLLM oder Cloud-Dienst. Lokale Adressen und Tailscale-Adressen umgehen den System-Proxy. Karte in den Einstellungen: Test connection, Warnung bei nicht lokaler Adresse, der API-Schlüssel wird unter Windows verschlüsselt gespeichert.
- **Der Agent sieht die Fotos**: mit aktiviertem „Agent sees photos“ sieht das Modell die Vorschauen und beschneidet und korrigiert die Farbe selbst.
- **Beschwerden über Ausdrucke in gewöhnlichen Worten** („zu rot“, „dunkler als der Bildschirm“, Farbstich in Schwarz-Weiß) passen die Druckkorrektur für den aktuellen Drucker und das Papier in festen Schritten an.
- Sicherheit: Der Agent sieht nur seinen Arbeitsordner (standardmäßig `Desktop\Печать ИИ`) und die Ordner und Dateien, die man im Chat eintippt; Drucken fragt vorher nach Erlaubnis (optional Automodus nach 3 Bestätigungen), führt immer die Druckvorprüfung durch und ist standardmäßig auf 20 Blatt pro Auftrag begrenzt; Testmodus ist standardmäßig eingeschaltet.
- Zuverlässigkeit: Stop unterbricht das Modell sofort; jeder Tool-Aufruf erhält eine ID und eine Antwort; Endlosschleifen und Runden über 15 Minuten werden abgebrochen; Roll back macht alle Änderungen des Agenten in der Unterhaltung rückgängig. Der Agent antwortet in der Sprache der Oberfläche; seine Texte sind in 13 weitere Oberflächensprachen übersetzt.
- Behoben: eine Anfrage mit falschem Schlüssel an den Agent-Endpunkt konnte mit abgebrochener Verbindung statt Fehler 401 enden.

Dateien im Release: `KopiTehnikPrint-Setup-1.9.0.exe`, `KopiTehnikPrint-Portable-1.9.0.exe`, `SHA256SUMS.txt`.

# Versionshinweise — v1.0.0 (erste Version)

Erste öffentliche Version von PhotoCrop (КопиТехник PRINT).

- Qt-Oberfläche (`PhotoCropQt.exe`) und das ältere Tkinter-Fenster (`photo_crop.py`).
- Zuschneiden und Drucken für 10×15 cm und weitere Formate bis A2.
- Intelligenter Zuschnitt (Gesichter, Personen, Haustiere), Farbkorrektur je Foto, ICC-Profil des Druckers.
- Druckplanung mit Prüfungen vor dem Druck, Beschnitt je Seite, ein Auftrag pro Blatt.
- KI-Agent-Modus und MCP-Server (`PhotoCropAgent.exe mcp`).
- Oberflächensprachen der Qt-Version: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча; die Übersetzungen sind maschinell und noch nicht von Muttersprachlern geprüft.
- Erkennungsmodelle werden bei der ersten Nutzung heruntergeladen. License: PolyForm Noncommercial 1.0.0

Dateien im Release: `PhotoCropQt.exe`, `PhotoCropAgent.exe`.