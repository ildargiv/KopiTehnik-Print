[English](RELEASE_NOTES.md) | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | **Português** | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Notas da versão — v1.9.0

- **Agente IA integrado «Print Assistant» (beta, desligado por padrão)**: aba de agente no painel direito e campo de entrada de duas linhas abaixo das abas (funciona em qualquer aba), botões rápidos Improve, Crop, Prepare, Print. Uma pasta digitada mais um botão é um comando; vários botões executam-se em ordem. Nada é enviado até que o agente esteja ativado e um endereço de modelo seja indicado.
- **Qualquer modelo compatível com OpenAI**: llama.cpp local, Ollama, vLLM ou serviço na nuvem. Endereços locais e de Tailscale não passam pelo proxy do sistema. Cartão de configurações: Test connection, aviso para endereço não local; a chave API é guardada cifrada no Windows.
- **O agente vê as fotos**: com «Agent sees photos» ligado, o modelo vê as pré-visualizações e recorta e corrige a cor por conta própria.
- **Queixas sobre a impressão em palavras normais** («demasiado rosa», «mais escuro que a tela», tom em preto e branco) ajustam a correção de impressão para a impressora e o papel atuais em passos fixos.
- Segurança: o agente só vê a sua pasta de trabalho (por padrão `Desktop\Печать ИИ`) e as pastas e arquivos que você digita no chat; a impressão pergunta primeiro (modo automático opcional após 3 confirmações), sempre executa a checagem prévia e é limitada por padrão a 20 folhas por impressão; o modo de teste está ligado por padrão.
- Confiabilidade: Stop interrompe o modelo na hora; cada chamada de ferramenta recebe um id e uma resposta; loops infinitos e turnos com mais de 15 minutos são parados; Roll back desfaz todas as mudanças do agente na conversa. O agente responde no idioma da interface; seus textos estão traduzidos para mais 13 idiomas de interface.
- Corrigido: uma solicitação com chave errada ao endpoint do agente podia terminar com a conexão derrubada em vez do erro 401.

Arquivos da versão: `KopiTehnikPrint-Setup-1.9.0.exe`, `KopiTehnikPrint-Portable-1.9.0.exe`, `SHA256SUMS.txt`.

# Notas da versão — v1.0.0 (primeira versão)

Primeira versão pública do PhotoCrop (КопиТехник PRINT).

- Interface Qt (`PhotoCropQt.exe`) e a janela Tkinter anterior (`photo_crop.py`).
- Recorte e impressão em 10×15 cm e outros formatos até A2.
- Recorte inteligente (rostos, pessoas, animais), correção de cor por foto, perfil ICC da impressora.
- Planejamento de impressão com verificações prévias, sangria por lado, um trabalho por folha.
- Modo agente de IA e servidor MCP (`PhotoCropAgent.exe mcp`).
- Idiomas da interface na versão Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча; as traduções são automáticas e ainda não foram revisadas por falantes nativos.
- Os modelos de detecção são baixados no primeiro uso. License: PolyForm Noncommercial 1.0.0

Arquivos da versão: `PhotoCropQt.exe`, `PhotoCropAgent.exe`.