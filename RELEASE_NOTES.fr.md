[English](RELEASE_NOTES.md) | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | **Français** | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Notes de version — v1.9.0

- **Agent IA intégré « Print Assistant » (bêta, désactivé par défaut)** : onglet agent dans le volet droit et champ de saisie sur deux lignes sous les onglets (fonctionne depuis n'importe quel onglet), boutons rapides Improve, Crop, Prepare, Print. Un dossier saisi plus un bouton forment une commande ; plusieurs boutons s'exécutent à la suite. Rien n'est envoyé tant que l'agent n'est pas activé et qu'une adresse de modèle n'est pas indiquée.
- **N'importe quel modèle compatible OpenAI** : llama.cpp local, Ollama, vLLM ou service cloud. Les adresses locales et Tailscale n'empruntent pas le proxy système. Carte des paramètres : Test connection, avertissement pour une adresse non locale, la clé API est stockée chiffrée sous Windows.
- **L'agent voit les photos** : avec « Agent sees photos » activé, le modèle regarde les aperçus et recadre et corrige la couleur lui-même.
- **Remarques sur l'impression en mots ordinaires** (« trop rose », « plus sombre que l'écran », teinte en noir et blanc ) règlent la correction d'impression pour l'imprimante et le papier actuels par paliers fixes.
- Sécurité : l'agent ne voit que son dossier de travail (`Desktop\Печать ИИ` par défaut) et les dossiers et fichiers qu'on saisit dans le chat ; l'impression demande d'abord l'autorisation (mode automatique facultatif après 3 confirmations), lance toujours le contrôle avant impression et est limitée par défaut à 20 feuilles par impression ; le mode essai est activé par défaut.
- Fiabilité : Stop interrompt le modèle sur-le-champ ; chaque appel d'outil reçoit un id et une réponse ; les boucles sans fin et les tours de plus de 15 minutes sont arrêtés ; Roll back annule tous les changements de l'agent dans la conversation. L'agent répond dans la langue de l'interface ; ses textes sont traduits dans 13 langues d'interface de plus.
- Corrigé : une requête avec une clé incorrecte vers le point de terminaison de l'agent pouvait se terminer par une connexion rompue au lieu de l'erreur 401.

Fichiers de la version : `KopiTehnikPrint-Setup-1.9.0.exe`, `KopiTehnikPrint-Portable-1.9.0.exe`, `SHA256SUMS.txt`.

# Notes de version — v1.0.0 (première version)

Première version publique de PhotoCrop (КопиТехник PRINT).

- Interface Qt (`PhotoCropQt.exe`) et ancienne fenêtre Tkinter (`photo_crop.py`).
- Recadrage et impression en 10×15 cm et autres formats jusqu'à A2.
- Recadrage intelligent (visages, personnes, animaux), correction des couleurs par photo, profil ICC de l'imprimante.
- Préparation de l'impression avec contrôles préalables, fond perdu par côté, un travail par feuille.
- Mode agent IA et serveur MCP (`PhotoCropAgent.exe mcp`).
- Langues de l'interface de la version Qt : Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча ; les traductions sont automatiques et pas encore relues par des locuteurs natifs.
- Les modèles de détection sont téléchargés à la première utilisation. License: PolyForm Noncommercial 1.0.0

Fichiers de la version : `PhotoCropQt.exe`, `PhotoCropAgent.exe`.