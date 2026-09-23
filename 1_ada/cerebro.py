"""
Cérebro da ADA — núcleo único.

Tudo que define "quem é a ADA" e como ela pensa mora aqui:
  - config do modelo (Qwen3.8-27B em GGUF 3 bits + adapter LoRA via ADA_ADAPTER)
  - system prompt por usuário (persona + base de conhecimento):
    SYSTEM, SYSTEM_CONVIDADO e SYSTEM_VISITANTE
  - carregar() do modelo no llama.cpp (tudo na GPU)
  - runtime de tools (responder / responder_stream / responder_eventos)

As interfaces (terminal, web, benchmark) só importam este módulo, montam o
histórico e chamam um dos responder(). Pra trocar o adapter, o system prompt ou
os parâmetros de geração, mexe SÓ aqui.

Fluxo de um turno (responder_eventos):
  1. monta o prompt com o template do Qwen e as tools no system (tools=POOL)
  2. pensa e responde na mesma geração, soltando eventos think/resp
  3. se a resposta trouxer <tool_call>: executa as tools, injeta os
     <tool_response> e fala de novo em cima dos resultados reais

Depende de llama-cpp-python, do pacote tools/ (funções reais) e de
1_ada/conhecimento (RAG). Persona com dados reais fica no personas_local.py (local).
"""
import atexit
import json
import os
import re
import sys
from itertools import chain
from pathlib import Path

from huggingface_hub import hf_hub_download
from llama_cpp import Llama
from transformers import AutoTokenizer

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "1_ada"))
from tools import EXECUTORES  # pacote 1_ada/tools/ (tools por categoria)
sys.path.insert(0, str(RAIZ / "1_ada" / "conhecimento"))
from conhecimento import carregar_conhecimento  # base de fatos confiáveis (RAG)

POOL = json.loads((Path(__file__).resolve().parent / "tools_pool.json").read_text(encoding="utf-8"))

# --- config do cérebro (fonte de verdade única) ---
# Eu rodo o Qwen3.8-27B em GGUF de 3 bits: é o maior que cabe nos 16GB sem ficar burro (2.5 bits perde ~6 pontos).
REPO = "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF"
ARQUIVO = "Qwen3.8-27B-GSQ-RCO-IQ3_XXS.gguf"
# Eu monto o prompt com o tokenizer do modelo original: é o mesmo template do treino, com tools e thinking.
BASE_HF = "Qwen/Qwen3.8-27B"
# Só 16 das 64 camadas guardam contexto (as outras são DeltaNet, memória fixa): 64KB por token, 16k custa ~1GB.
N_CTX = 16384
# Eu escolho a versão com ADA_ADAPTER (pasta em _modelo/ com o adapter.gguf); o padrão é a ADA 27B que eu treinei.
# ADA_ADAPTER="" roda o 27B cru, sem LoRA.
_NOME_ADAPTER = os.environ.get("ADA_ADAPTER", "ada_v12_1_en_a16_27b")
ADAPTER = str(RAIZ / "_modelo" / _NOME_ADAPTER) if _NOME_ADAPTER else "qwen3.8_27b_cru"
# Eu mantenho esses params como padrão do meu modelo para o equilíbrio entre qualidade e estabilidade.
GEN = dict(max_tokens=4096, temperature=0.5, top_p=0.9, repeat_penalty=1.0, stop=["<|im_end|>"])


PERSONA_VICTOR = "Current user: Victor, your creator. Be direct and objective, don't make things up."
# Eu mantenho a persona do visitante genérica no repo e deixo os dados reais em personas_local.py.
PERSONA_VISITANTE = ("Current user: visitor (not Victor, not your creator). "
                     "Be kind and objective, don't make things up.")
PERSONA_CONVIDADO = PERSONA_VISITANTE
try:
    from personas_local import PERSONA_CONVIDADO  # sobrescreve com a pessoa real, se existir
except ImportError:
    pass


def montar_system(persona=PERSONA_VICTOR):
    """Eu monto o system prompt: a persona de quem está falando + a base de conhecimento."""
    partes = [persona]
    if os.environ.get("ADA_BASE", "on") != "off":
        base = carregar_conhecimento()
        if base:
            partes.append(base)
    return "\n\n".join(partes)


SYSTEM = montar_system()              # texto / web (Victor)
SYSTEM_CONVIDADO = montar_system(persona=PERSONA_CONVIDADO)  # web: IP do convidado (.env)
SYSTEM_VISITANTE = montar_system(persona=PERSONA_VISITANTE)  # web: qualquer outro IP


def carregar():
    """Eu abro o GGUF no llama.cpp com tudo na GPU e pego o tokenizer só pra montar o prompt."""
    lora = str(Path(ADAPTER) / "adapter.gguf") if _NOME_ADAPTER else None
    # flash_attn: sem ele a atenção monta uma matriz de ~800MB com 16k de contexto e estoura a GPU
    llm = Llama(model_path=hf_hub_download(REPO, ARQUIVO), n_ctx=N_CTX, n_gpu_layers=-1,
                flash_attn=True, lora_path=lora, verbose=False)
    # fecho o modelo antes do Python encerrar: sem isso o Metal é desligado com a memória da GPU
    # ainda registrada e o processo aborta na saída (GGML_ASSERT, código 134) — com LoRA sempre acontece
    atexit.register(llm.close)
    tok = AutoTokenizer.from_pretrained(BASE_HF)
    return llm, tok, None  # devolvo 3 coisas como antes: interface, terminal e benchmark não mudam


def parse_tool_calls(texto):
    """Eu extraio todas as chamadas de tool do texto para executar no turno."""
    chamadas = []
    for bloco in re.findall(r"<tool_call>(.*?)</tool_call>", texto, re.DOTALL):
        fn = re.search(r"<function=(\w+)>", bloco)
        if not fn:
            continue
        args = {k: v.strip() for k, v in
                re.findall(r"<parameter=(\w+)>\s*(.*?)\s*</parameter>", bloco, re.DOTALL)}
        chamadas.append((fn.group(1), args))
    return chamadas


def executar(nome, args):
    """Eu executo a função real da tool e devolvo a mensagem em vez de explodir o programa."""
    fn = EXECUTORES.get(nome)
    if not fn:
        return f"tool '{nome}' not implemented yet"
    try:
        return fn(**args)
    except Exception as e:
        return f"error in tool {nome}: {e}"


FIM_THINK, TOOL = "</think>", "<tool_call>"


def _gerar(llm, tok, hist, pensando, gen_kw):
    """Eu monto o prompt com o template oficial e vou soltando o texto conforme o modelo gera."""
    # preserve_thinking=False: falas antigas entram sem bloco de raciocínio, igual ao treino
    # (no padrão o 3.8 enfia um <think></think> vazio em cada uma)
    prompt = tok.apply_chat_template(hist, tools=POOL, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=pensando, preserve_thinking=False)
    for pedaco in llm(prompt, stream=True, **gen_kw):
        yield pedaco["choices"][0]["text"]


def _seguro(texto, marcas):
    """Eu seguro o finalzinho do texto quando ele pode ser o começo de uma tag que ainda não chegou inteira."""
    for n in range(min(len(texto), max(map(len, marcas)) - 1), 0, -1):
        if any(m.startswith(texto[-n:]) for m in marcas):
            return texto[:-n]
    return texto


def _partes(buf, pensando, final=False):
    """Eu divido o texto gerado em (raciocínio, resposta, se o raciocínio fechou); do <tool_call> em diante nada aparece."""
    guarda = (lambda t, _: t) if final else _seguro
    think, resto, fechou = "", buf, not pensando
    if pensando:
        cortes = [buf.find(m) for m in (FIM_THINK, TOOL) if m in buf]
        if not cortes:
            return guarda(buf, (FIM_THINK, TOOL)), "", False
        think, resto, fechou = buf[:min(cortes)], buf[min(cortes):].removeprefix(FIM_THINK), True
    resp = resto.lstrip()
    corte = resp.find(TOOL)
    resp = resp[:corte] if corte >= 0 else guarda(resp, (TOOL,))
    return think, resp, fechou


def _fases(llm, tok, hist, pensando, gen_kw):
    """Eu gero UMA vez e solto 'think' até o </think> e 'resp' depois dele; no fim devolvo o texto cru inteiro."""
    buf, ditos = "", {"think": 0, "resp": 0}
    for pedaco in chain(_gerar(llm, tok, hist, pensando, gen_kw), [None]):  # None = acabou, solto o que segurei
        buf += pedaco or ""
        think, resp, _ = _partes(buf, pensando, final=pedaco is None)
        for tipo, texto in (("think", think), ("resp", resp)):
            if len(texto) > ditos[tipo]:
                yield {"t": tipo, "d": texto[ditos[tipo]:]}
                ditos[tipo] = len(texto)
    return buf


def _falar(llm, tok, hist, gen_kw):
    """Eu penso e respondo na mesma geração; se o raciocínio estourar o max_tokens sem fechar, respondo sem pensar."""
    saida = yield from _fases(llm, tok, hist, True, gen_kw)
    if not _partes(saida, True, final=True)[2]:
        saida = yield from _fases(llm, tok, hist, False, gen_kw)
    return saida


def _como_mensagem(saida):
    """Eu devolvo a fala da tool pro histórico do jeito que o Qwen3.8 lê: raciocínio no campo dele, não no texto."""
    if FIM_THINK not in saida:
        return {"role": "assistant", "content": saida.strip()}
    think, resto = saida.split(FIM_THINK, 1)
    return {"role": "assistant", "content": resto.strip(), "reasoning_content": think.strip()}


def responder_eventos(llm, tok, config, historico, **gen_kw):
    """Eu rodo a conversa inteira e solto eventos pra quem estiver ouvindo (interface, terminal e benchmark).
    Eventos: {"t":"think","d":txt} | {"t":"tool","nome","args","res"} | {"t":"resp","d":txt} | {"t":"fim"}"""
    gen_kw.pop("enable_thinking", None)  # o thinking e controlado aqui dentro, nao vai pro generate

    # 1) PENSAR E RESPONDER — a resposta sai da mesma geração do raciocínio, então ela segue o que pensou
    saida = yield from _falar(llm, tok, historico, gen_kw)

    # 2) TOOLS — executa todas e ela pensa de novo em cima dos resultados REAIS antes de responder
    chamadas = parse_tool_calls(saida)
    if chamadas:
        respostas = []
        for nome, args in chamadas:
            resultado = executar(nome, args)
            yield {"t": "tool", "nome": nome, "args": args, "res": str(resultado)}
            respostas.append(f"<tool_response>\n{resultado}\n</tool_response>")
        hist2 = historico + [_como_mensagem(saida), {"role": "user", "content": "\n".join(respostas)}]
        yield from _falar(llm, tok, hist2, gen_kw)
    yield {"t": "fim"}


def responder(llm, tok, config, historico, **gen_kw):
    """Eu rodo o MESMO fluxo da interface e só junto o resultado: o que o benchmark mede é o que a interface entrega."""
    resposta, passos = "", []
    for ev in responder_eventos(llm, tok, config, historico, **gen_kw):
        if ev["t"] == "resp":
            resposta += ev["d"]
        elif ev["t"] == "tool":
            passos.append((ev["nome"], ev["args"], ev["res"]))
    return resposta.strip(), passos or None


def responder_stream(llm, tok, config, historico, **gen_kw):
    """Eu mostro o mesmo fluxo ao vivo no terminal: raciocínio em cinza, tool em amarelo e resposta em ciano."""
    abre = {"think": "\033[2m💭 ", "resp": "\033[96mADA>\033[0m "}
    resposta, passos, atual = "", [], None
    for ev in responder_eventos(llm, tok, config, historico, **gen_kw):
        if ev["t"] in abre:
            if ev["t"] != atual:  # mudou de fase: fecho a cor anterior e abro a nova
                print(("\033[0m\n" if atual else "") + abre[ev["t"]], end="", flush=True)
                atual = ev["t"]
            print(ev["d"], end="", flush=True)
            if ev["t"] == "resp":
                resposta += ev["d"]
        elif ev["t"] == "tool":
            print(("\033[0m\n" if atual else "") + f"\033[93m[{ev['nome']} → {ev['res']}]\033[0m")
            passos.append((ev["nome"], ev["args"], ev["res"]))
            atual = None
    print("\033[0m")
    return resposta.strip(), passos or None
