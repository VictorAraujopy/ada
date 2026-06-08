# ADA — IA pessoal 100% local

> Uma assistente de IA que roda **inteira no Mac** (Apple Silicon, MLX): personalidade própria treinada nos pesos, voz clonada e controle real do sistema. Sem nuvem, sem servidor, offline.

A **ADA** é o que sai do projeto **core**: um Qwen3.5-9B com um adapter LoRA treinado do zero pra ter um jeito próprio — seca, direta, com gostos e opiniões — e ligado às ferramentas do macOS. O nome vem da **Ada Wong** (Resident Evil). A ideia: uma IA que seja **do Victor de verdade**, não um assistente genérico atuando um papel.

## O que ela faz

- **Conversa** por texto e por **voz** (ouve com Whisper, responde falando com voz clonada)
- **Age no Mac**: hora, status (bateria/RAM/disco/Wi-Fi), volume, brilho, tema, abrir/fechar apps, música, screenshot, busca de arquivo, lembretes
- **Pensa antes de responder** (modo *thinking*) e decide sozinha quando usar uma ferramenta
- **100% local e offline** — nada sai da máquina
- Roda residente como **daemon** (atalho de teclado) ou no terminal

## Arquitetura

| Pasta | O que é |
|---|---|
| `1_modelo/` | os adapters LoRA (os "cérebros" em formato MLX) |
| `3_chat/` | chat de texto no terminal |
| `4_voz/` | pipeline de voz (Whisper → 9B → tradução → TTS) |
| `5_conhecimento/` | base de fatos (anti-alucinação) |
| `6_assistente/` | runtime de ferramentas + daemon residente |
| `7_interface/` | interface web (demo) |

> O **dataset de personalidade** e o **pipeline de treino** são proprietários e **não** fazem parte deste repositório — é o "molho" da ADA.

## Como rodar

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python 3_chat/chat_ada.py     # chat de texto
python 4_voz/ada_voz.py       # voz: você fala, ela responde falando
```

O adapter atual (`ada_v9_9b`) já vem incluído; o modelo base **Qwen3.5-9B** é baixado automaticamente na primeira execução (~5 GB). Env var útil: `ADA_BASE=off` (testa o LoRA puro, sem a base de fatos).

## Como foi treinada

Fine-tuning **LoRA (QLoRA 4-bit)** sobre o Qwen3.5-9B, numa GPU na nuvem, convertido depois pro formato MLX pra rodar local. O dataset de personalidade e os scripts de treino são proprietários.

## Stack

`Qwen3.5-9B` · `MLX` · `LoRA / QLoRA` · `Whisper` · `Qwen3-TTS` (voz clonada) · `FastAPI` · Mac M4 16GB

## Licença

**Todos os direitos reservados** — ver [LICENSE](LICENSE). Código disponível para visualização; uso, cópia, modificação ou redistribuição requerem permissão expressa do autor.
