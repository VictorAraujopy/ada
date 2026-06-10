"""
Cérebro da ADA — núcleo único.

Tudo que define "quem é a ADA" e como ela pensa mora aqui:
  - config do modelo (base + adapter LoRA)
  - system prompt (com a variação pra voz)
  - carregar() do cérebro
  - runtime de tools (responder / responder_stream / responder_eventos)

As interfaces (terminal, voz, web, testes) só importam este módulo, montam o
histórico e chamam um dos responder(). Pra trocar o adapter, o system prompt ou
os parâmetros de geração, mexe SÓ aqui.

Fluxo de um turno (responder):
  1. monta o prompt com as tools no system (apply_chat_template tools=POOL)
  2. gera -> se a ADA emitir <tool_call>: parseia (funcao + args), EXECUTA, injeta o
     <tool_response> e gera DE NOVO -> resposta final
  3. se nao emitir: e a resposta direta

Depende de mlx_vlm, do pacote tools/ (funcoes reais) e de 5_conhecimento (RAG).
"""
import json
import os
import re
import sys
from pathlib import Path

from mlx_vlm import load, generate, stream_generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.trainer.utils import apply_lora_layers

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "6_assistente"))
from tools import EXECUTORES  # pacote 6_assistente/tools/ (tools por categoria)
sys.path.insert(0, str(RAIZ / "5_conhecimento"))
from conhecimento import carregar_conhecimento  # base de fatos confiáveis (RAG)

POOL = json.loads((RAIZ / "2_treino" / "v6_tools" / "tools_pool.json").read_text(encoding="utf-8"))

# --- config do cérebro (fonte de verdade única) ---
MODELO = "mlx-community/Qwen3.5-9B-MLX-4bit"
# ADA_ADAPTER escolhe a versão (default ada_v10_9b, o 9B treinado na nuvem); ADA_ADAPTER=ada_v5 volta pro antigo
ADAPTER = str(RAIZ / "1_modelo" / os.environ.get("ADA_ADAPTER", "ada_v10_9b"))
# parametros de geracao padrao (canonico: veio do chat de texto)
#   max_tokens solto: nunca corta o think+resposta, teto so de seguranca (anti-loop)
#   temperature 0.5: o 9B aguenta mais solta sem virar aleatorio
#   top_p 0.9: corta a cauda improvavel (anti-alucinacao) sem ficar decorado
#   repetition_penalty 1.0: leve, o 9B repete bem menos que o 7B
GEN = dict(max_tokens=4096, temperature=0.5, top_p=0.9, repetition_penalty=1.0)


def montar_system(voz=False):
    """Monta o system prompt da ADA. voz=True acrescenta a instrucao de fala (direto ao
    ponto + usar ferramentas). A base de conhecimento (RAG) entra no fim, a menos que
    ADA_BASE=off (teste do cerebro puro, sem fatos injetados)."""
    partes = ["Usuário atual: Victor, seu criador. Seja direta e objetiva não invente informações."]
    if voz:
        partes.append("Você responde por voz, então vá direto ao ponto. Se o pedido pede uma "
                       "ferramenta (hora, status, app, música...), use a ferramenta — você não "
                       "tem relógio nem sensores próprios.")
    if os.environ.get("ADA_BASE", "on") != "off":
        base = carregar_conhecimento()
        if base:
            partes.append(base)
    return "\n\n".join(partes)


SYSTEM = montar_system()              # texto / web
SYSTEM_VOZ = montar_system(voz=True)  # voz


def carregar():
    """Carrega o base (Qwen3.5-9B) e aplica o LoRA da ADA. Retorna (model, processor, config)."""
    model, processor = load(MODELO, processor_config={"trust_remote_code": True})
    config = model.config.__dict__
    model = apply_lora_layers(model, ADAPTER)
    return model, processor, config


def parse_tool_calls(texto):
    """Extrai TODAS as (funcao, args) dos <tool_call> do texto — a ADA pode pedir varias
    num turno so (ex: fechar 2 apps). Lista vazia se nao houver nenhuma."""
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
    """Roda a funcao real da tool. Desconhecida -> mensagem (nao explode)."""
    fn = EXECUTORES.get(nome)
    if not fn:
        return f"tool '{nome}' ainda nao implementada"
    try:
        return fn(**args)
    except Exception as e:
        return f"erro na tool {nome}: {e}"


def _limpa(texto):
    """Tira o raciocinio. Com thinking ON, o <think> de ABERTURA fica no prompt, entao a
    saida vem 'RACIOCINIO</think>RESPOSTA' -> pega so o que vem depois do </think>."""
    if "</think>" in texto:
        texto = texto.rsplit("</think>", 1)[-1]
    return texto.strip()


def responder(model, processor, config, historico, **gen_kw):
    """Gera a resposta; se a ADA chamar uma tool, executa e gera a final.
    Retorna (resposta, passo_tool) — passo_tool = (nome, args, resultado) ou None."""
    gen_kw.pop("enable_thinking", None)  # o thinking e controlado aqui dentro, nao vai pro generate

    def _gen(hist, thinking=True):
        prompt = apply_chat_template(processor, config, hist, add_generation_prompt=True,
                                     num_images=0, enable_thinking=thinking, tools=POOL)
        r = generate(model, processor, prompt, **gen_kw)
        out = (r.text if hasattr(r, "text") else str(r)).strip()
        # se o raciocinio estourou o max_tokens SEM fechar </think>, ele vazaria CRU pro usuario.
        # nesse caso re-gera SEM thinking -> resposta direta e limpa (a ADA ja e treinada assim).
        if thinking and "</think>" not in out:
            return _gen(hist, thinking=False)
        return out

    saida = _gen(historico)
    chamadas = parse_tool_calls(saida)
    if not chamadas:
        return _limpa(saida), None

    # executa TODAS as tools pedidas; a ADA responde com base nos resultados REAIS (sem alucinar)
    passos, respostas = [], []
    for nome, args in chamadas:
        resultado = executar(nome, args)
        passos.append((nome, args, resultado))
        respostas.append(f"<tool_response>\n{resultado}\n</tool_response>")
    hist2 = historico + [
        {"role": "assistant", "content": saida},
        {"role": "user", "content": "\n".join(respostas)},
    ]
    return _limpa(_gen(hist2)), passos


def _token(chunk):
    """Texto novo de um chunk do stream_generate (str ou objeto com .text)."""
    return chunk if isinstance(chunk, str) else (getattr(chunk, "text", "") or "")


def responder_stream(model, processor, config, historico, **gen_kw):
    """MODO DEMO (pro video): streama o raciocinio AO VIVO (cinza) ate o </think>, executa
    as tools, e streama a resposta final ao vivo. Printa direto no terminal.
    Retorna (resposta, passos) como o responder() normal."""
    gen_kw.pop("enable_thinking", None)

    def pensa(hist):
        prompt = apply_chat_template(processor, config, hist, add_generation_prompt=True,
                                     num_images=0, enable_thinking=True, tools=POOL)
        buf, impresso = "", 0   # impresso = nº de chars do raciocinio ja mostrados (None = parou)
        print("\033[2m💭 ", end="", flush=True)  # cinza
        for chunk in stream_generate(model, processor, prompt, **gen_kw):
            buf += _token(chunk)
            if impresso is None:
                continue                              # think ja fechou; so acumula (pro tool_call)
            visivel = buf.split("</think>", 1)[0]     # so o raciocinio, SEM a tag
            if len(visivel) > impresso:
                # mostra o pedaco novo — inclui a ULTIMA palavra mesmo grudada no </think>
                print(visivel[impresso:], end="", flush=True)
                impresso = len(visivel)
            if "</think>" in buf:
                print("\033[0m", flush=True)          # fecha o cinza e para de mostrar
                impresso = None
        if impresso is not None:
            print("\033[0m", flush=True)
        return buf

    def fala(hist):
        prompt = apply_chat_template(processor, config, hist, add_generation_prompt=True,
                                     num_images=0, enable_thinking=False, tools=POOL)
        print("\033[96mADA>\033[0m ", end="", flush=True)
        out = ""
        for chunk in stream_generate(model, processor, prompt, **gen_kw):
            t = _token(chunk)
            out += t
            print(t, end="", flush=True)            # resposta ao vivo
        print()
        return out.strip()

    saida = pensa(historico)
    chamadas = parse_tool_calls(saida)
    passos, hist_final = None, historico
    if chamadas:
        passos, respostas = [], []
        for nome, args in chamadas:
            resultado = executar(nome, args)
            passos.append((nome, args, resultado))
            respostas.append(f"<tool_response>\n{resultado}\n</tool_response>")
            print(f"\033[93m[{nome} → {resultado}]\033[0m")
        hist_final = historico + [
            {"role": "assistant", "content": saida},
            {"role": "user", "content": "\n".join(respostas)},
        ]
    return fala(hist_final), passos  # SEMPRE streama a resposta ao vivo (com ou sem tool)


def responder_eventos(model, processor, config, historico, **gen_kw):
    """Como o responder_stream, mas YIELDA eventos (pra interface web) em vez de printar.
    Eventos: {"t":"think","d":txt} | {"t":"tool","nome","args","res"} | {"t":"resp","d":txt} | {"t":"fim"}
    Quem chama acumula os 'resp' pra montar a resposta final e guardar no historico."""
    gen_kw.pop("enable_thinking", None)

    def _stream(hist, thinking):
        prompt = apply_chat_template(processor, config, hist, add_generation_prompt=True,
                                     num_images=0, enable_thinking=thinking, tools=POOL)
        for chunk in stream_generate(model, processor, prompt, **gen_kw):
            yield _token(chunk)

    # 1) PENSAR — emite so o raciocinio (ate o </think>), com o fix da ultima palavra
    buf, impresso = "", 0
    for tok in _stream(historico, True):
        buf += tok
        if impresso is None:
            continue
        visivel = buf.split("</think>", 1)[0]
        if len(visivel) > impresso:
            yield {"t": "think", "d": visivel[impresso:]}
            impresso = len(visivel)
        if "</think>" in buf:
            impresso = None
    saida = buf

    # 2) TOOLS — executa todas, um evento por tool
    chamadas = parse_tool_calls(saida)
    hist_final = historico
    if chamadas:
        respostas = []
        for nome, args in chamadas:
            resultado = executar(nome, args)
            yield {"t": "tool", "nome": nome, "args": args, "res": str(resultado)}
            respostas.append(f"<tool_response>\n{resultado}\n</tool_response>")
        hist_final = historico + [
            {"role": "assistant", "content": saida},
            {"role": "user", "content": "\n".join(respostas)},
        ]

    # 3) FALAR — streama a resposta final (sem thinking)
    for tok in _stream(hist_final, False):
        yield {"t": "resp", "d": tok}
    yield {"t": "fim"}
