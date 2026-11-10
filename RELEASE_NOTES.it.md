[English](RELEASE_NOTES.md) | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | **Italiano** | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Note di rilascio — v1.9.0

- **Agente IA integrato «Print Assistant» (beta, spento per impostazione predefinita)**: scheda agente nel riquadro destro e campo di input su due righe sotto le schede (funziona da qualsiasi scheda), pulsanti rapidi Improve, Crop, Prepare, Print. Una cartella scritta più un pulsante è un comando; più pulsanti vengono eseguiti in ordine. Nulla viene inviato finché l'agente non è attivato e non è indicato un indirizzo del modello.
- **Qualunque modello compatibile con OpenAI**: llama.cpp locale, Ollama, vLLM o un servizio cloud. Gli indirizzi locali e di Tailscale bypassano il proxy di sistema. Scheda nelle impostazioni: Test connection, avviso per un indirizzo non locale, la chiave API è archiviata cifrata su Windows.
- **L'agente vede le foto**: con «Agent sees photos» attivo, il modello guarda le anteprime e da solo ritaglia e corregge il colore.
- **Rimproveri sulla stampa in parole ordinarie** («troppo rosa», «più scuro dello schermo», cast di colore in bianco e nero) regolano la correzione di stampa per la stampante e la carta in uso con passi fissi.
- Sicurezza: l'agente vede solo la sua cartella di lavoro (predefinita `Desktop\Печать ИИ`) e le cartelle e i file scritti nella chat; la stampa chiede prima il permesso (modalità automatica facoltativa dopo 3 conferme), sempre esegue il controllo prima della stampa ed è limitata per impostazione predefinita a 20 fogli per stampa; la modalità prova è attiva per impostazione predefinita.
- Affidabilità: Stop interrompe il modello all'istante; ogni chiamata di strumento riceve un id e una risposta; cicli senza fine e turni oltre 15 minuti vengono interrotti; Roll back annulla tutte le modifiche dell'agente nella conversazione. L'agente risponde nella lingua dell'interfaccia; i suoi testi sono tradotti in altre 13 lingue dell'interfaccia.
- Risolto: una richiesta con una chiave errata al endpoint dell'agente poteva finire con la connessione interrotta invece che con l'errore 401.

File della versione: `KopiTehnikPrint-Setup-1.9.0.exe`, `KopiTehnikPrint-Portable-1.9.0.exe`, `SHA256SUMS.txt`.

# Note di rilascio — v1.0.0 (prima versione)

Prima versione pubblica di PhotoCrop (КопиТехник PRINT).

- Interfaccia Qt (`PhotoCropQt.exe`) e la vecchia finestra Tkinter (`photo_crop.py`).
- Ritaglio e stampa in 10×15 cm e altri formati fino ad A2.
- Ritaglio intelligente (volti, persone, animali), correzione colore per foto, profilo ICC della stampante.
- Pianificazione della stampa con controlli preliminari, abbondanza per lato, un lavoro per foglio.
- Modalità agente IA e server MCP (`PhotoCropAgent.exe mcp`).
- Lingue dell'interfaccia della versione Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча; le traduzioni sono automatiche e non ancora riviste da madrelingua.
- I modelli di rilevamento vengono scaricati al primo utilizzo. License: PolyForm Noncommercial 1.0.0

File della versione: `PhotoCropQt.exe`, `PhotoCropAgent.exe`.