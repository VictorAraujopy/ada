"""Cérebro da ADA: configura, carrega o modelo e responde em eventos (pensar, tools e resposta)."""
import atexit
import ctypes
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

import llama_cpp
from huggingface_hub import hf_hub_download
from llama_cpp import Llama
from transformers import AutoTokenizer

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "1_ada"))
from tools import EXECUTORES

FIM_THINK, TOOL = "</think>", "<tool_call>"
INICIO_DA_CONVERSA, INICIO_DA_RESPOSTA = "<|im_start|>user", "<|im_start|>assistant"


@dataclass(frozen=True)
class Config:
    """Eu guardo tudo que um processo meu usa: modelo, contexto, sampling, tools e o system de cada usuário."""

    adapter: str
    pasta_adapter: Path | None
    repo_base: str
    arquivo_base: str
    tokenizer: str
    n_ctx: int
    n_ubatch: int
    geracao: dict
    pool: list
    systems: dict
    pasta_memorias: Path
    maximo_memorias: int


def configurar():
    """Eu monto a configuração do processo a partir do ADA_ADAPTER, do tools_pool.json e das personas."""
    nome_adapter = os.environ.get("ADA_ADAPTER", "ada_1_0_27b")
    persona_visitante = "Current user: visitor (not Victor, not your creator). Be kind, don't make things up."
    return Config(
        adapter=nome_adapter or "qwen3.8_27b_cru",
        pasta_adapter=RAIZ / "_modelo" / nome_adapter if nome_adapter else None,
        repo_base="ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF",
        arquivo_base="Qwen3.8-27B-GSQ-RCO-IQ3_XXS.gguf",
        tokenizer="Qwen/Qwen3.8-27B",
        n_ctx=16384,
        n_ubatch=128,
        geracao=dict(max_tokens=4096, temperature=0.7, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0,
                     repeat_penalty=1.0, stop=["<|im_end|>"]),
        pool=json.loads((RAIZ / "1_ada" / "tools_pool.json").read_text(encoding="utf-8")),
        systems={
            "victor": "Current user: Victor, your creator. Don't make things up.",
            "convidado": _persona_do_convidado(persona_visitante),
            "visitante": persona_visitante,
        },
        pasta_memorias=Path.home() / "Library" / "Caches" / "ada" / "memorias",
        maximo_memorias=6,
    )


def _persona_do_convidado(padrao):
    """Eu uso a persona real do personas_local.py (fora do git) quando ele existe."""
    try:
        from personas_local import PERSONA_CONVIDADO
    except ImportError:
        return padrao
    return PERSONA_CONVIDADO


class Modelo(Llama):
    """Eu sou o Llama com memórias em disco: retomo do maior começo de prompt já lido em vez de reler tudo."""

    def __init__(self, pasta_memorias, maximo_memorias, **kwargs):
        """Eu abro o modelo e a minha pasta de memórias, limpando as de processos que já acabaram."""
        super().__init__(**kwargs)
        _apagar_memorias_de_processos_mortos(pasta_memorias)
        self.pasta_memorias = pasta_memorias / str(os.getpid())
        self.pasta_memorias.mkdir(parents=True, exist_ok=True)
        atexit.register(shutil.rmtree, self.pasta_memorias, True)
        self.maximo_memorias = maximo_memorias
        self.memorias = {}
        self.continuar = False

    def generate(self, tokens, **kwargs):
        """Eu sigo da memória carregada quando `continuar` está ligado, sem tentar reaproveitar o prefixo."""
        if self.continuar:
            kwargs["reset"] = False
        return super().generate(tokens, **kwargs)

    def retomar(self, tokens):
        """Eu carrego a memória salva que cobre o maior começo de `tokens` e devolvo quantos tokens ela já leu."""
        cobrem = [arquivo for arquivo, lidos in self.memorias.items() if tokens[: len(lidos)] == lidos]
        if not cobrem:
            self.reset()
            return 0
        arquivo = max(cobrem, key=lambda candidato: len(self.memorias[candidato]))
        lidos = self.memorias.pop(arquivo)
        buffer_de_tokens = (llama_cpp.llama_token * self.n_ctx())()
        quantos = ctypes.c_size_t()
        carregou = llama_cpp.llama_state_load_file(self._ctx.ctx, str(arquivo).encode(), buffer_de_tokens,
                                                   self.n_ctx(), ctypes.byref(quantos))
        if not carregou:
            self.reset()
            return 0
        self.memorias[arquivo] = lidos
        self.n_tokens = len(lidos)
        self.input_ids[: len(lidos)] = lidos
        return len(lidos)

    def guardar(self, tokens):
        """Eu salvo em disco a memória que leu exatamente `tokens` e apago a menos usada se passar do máximo."""
        arquivo = self.pasta_memorias / f"{len(tokens)}-{hash(tuple(tokens)) & 0xFFFFFFFF:08x}.bin"
        llama_cpp.llama_state_save_file(self._ctx.ctx, str(arquivo).encode(),
                                        (llama_cpp.llama_token * len(tokens))(*tokens), len(tokens))
        self.memorias.pop(arquivo, None)
        self.memorias[arquivo] = list(tokens)
        while len(self.memorias) > self.maximo_memorias:
            mais_antiga = next(iter(self.memorias))
            del self.memorias[mais_antiga]
            mais_antiga.unlink(missing_ok=True)


def _apagar_memorias_de_processos_mortos(raiz):
    """Eu apago as pastas de memória de processos que já acabaram (cada processo vivo tem a sua)."""
    for pasta in raiz.glob("*"):
        try:
            os.kill(int(pasta.name), 0)
        except (ValueError, ProcessLookupError):
            shutil.rmtree(pasta, ignore_errors=True)
        except PermissionError:
            pass


def carregar(config=None):
    """Eu abro o GGUF com tudo na GPU, pego o tokenizer do Qwen e devolvo (modelo, tokenizer, config)."""
    config = config or configurar()
    gguf, lora = _arquivos_do_modelo(config)
    modelo = Modelo(config.pasta_memorias, config.maximo_memorias, model_path=gguf, n_ctx=config.n_ctx,
                    n_gpu_layers=-1, flash_attn=True, n_ubatch=config.n_ubatch, lora_path=lora, verbose=False)
    atexit.register(modelo.close)
    tok = AutoTokenizer.from_pretrained(config.tokenizer)
    return modelo, tok, config


def _arquivos_do_modelo(config):
    """Eu devolvo (gguf, lora): a ADA fundida roda sozinha; o adapter vai em cima do 27B da ISTA."""
    if config.pasta_adapter and (config.pasta_adapter / "ada.gguf").exists():
        return str(config.pasta_adapter / "ada.gguf"), None
    base = hf_hub_download(config.repo_base, config.arquivo_base)
    lora = str(config.pasta_adapter / "adapter.gguf") if config.pasta_adapter else None
    return base, lora


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


def _gerar(modelo, tok, config, hist, pensando, gen_kw):
    """Eu monto o prompt, retomo da maior memória salva, guardo os pontos reaproveitáveis e solto o texto."""
    prompt = tok.apply_chat_template(hist, tools=config.pool, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=pensando, preserve_thinking=False)
    inteiro = modelo.tokenize(prompt.encode("utf-8"), special=True)
    comeco_fixo = modelo.tokenize(prompt[:prompt.index(INICIO_DA_CONVERSA)].encode("utf-8"), special=True)
    ate_a_pergunta = modelo.tokenize(prompt[:prompt.rindex(INICIO_DA_RESPOSTA)].encode("utf-8"), special=True)
    paradas = [parada for parada in (comeco_fixo, ate_a_pergunta) if inteiro[: len(parada)] == parada]

    lidos = modelo.retomar(inteiro)
    for parada in paradas:
        if lidos < len(parada):
            modelo.eval(parada[lidos:])
            modelo.guardar(parada)
            lidos = len(parada)

    espaco = config.n_ctx - len(inteiro)
    geracao = {**gen_kw, "max_tokens": min(gen_kw.get("max_tokens", espaco), espaco)}
    modelo.continuar = True
    try:
        for pedaco in modelo(inteiro[lidos:], stream=True, **geracao):
            yield pedaco["choices"][0]["text"]
    finally:
        modelo.continuar = False


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


def _fases(modelo, tok, config, hist, pensando, gen_kw):
    """Eu gero UMA vez e solto 'think' até o </think> e 'resp' depois dele; no fim devolvo o texto cru inteiro."""
    buf, ditos = "", {"think": 0, "resp": 0}
    for pedaco in chain(_gerar(modelo, tok, config, hist, pensando, gen_kw), [None]):
        buf += pedaco or ""
        think, resp, _ = _partes(buf, pensando, final=pedaco is None)
        for tipo, texto in (("think", think), ("resp", resp)):
            if len(texto) > ditos[tipo]:
                yield {"t": tipo, "d": texto[ditos[tipo]:]}
                ditos[tipo] = len(texto)
    return buf


def _falar(modelo, tok, config, hist, gen_kw):
    """Eu penso e respondo na mesma geração; se o raciocínio estourar o max_tokens sem fechar, respondo sem pensar."""
    saida = yield from _fases(modelo, tok, config, hist, True, gen_kw)
    if not _partes(saida, True, final=True)[2]:
        saida = yield from _fases(modelo, tok, config, hist, False, gen_kw)
    return saida


def _como_mensagem(saida):
    """Eu devolvo a fala da tool pro histórico do jeito que o Qwen3.8 lê: raciocínio no campo dele, não no texto."""
    if FIM_THINK not in saida:
        return {"role": "assistant", "content": saida.strip()}
    think, resto = saida.split(FIM_THINK, 1)
    return {"role": "assistant", "content": resto.strip(), "reasoning_content": think.strip()}


def responder_eventos(modelo, tok, config, historico, **gen_kw):
    """Eu rodo a conversa e solto eventos think/tool/resp/fim, pensando de novo em cima do resultado das tools."""
    gen_kw.pop("enable_thinking", None)
    saida = yield from _falar(modelo, tok, config, historico, gen_kw)
    chamadas = parse_tool_calls(saida)
    if chamadas:
        respostas = []
        for nome, args in chamadas:
            resultado = executar(nome, args)
            yield {"t": "tool", "nome": nome, "args": args, "res": str(resultado)}
            respostas.append(f"<tool_response>\n{resultado}\n</tool_response>")
        hist2 = historico + [_como_mensagem(saida), {"role": "user", "content": "\n".join(respostas)}]
        yield from _falar(modelo, tok, config, hist2, gen_kw)
    yield {"t": "fim"}


def responder(modelo, tok, config, historico, **gen_kw):
    """Eu rodo o MESMO fluxo da interface e só junto o resultado: o que o benchmark mede é o que a interface entrega."""
    resposta, passos = "", []
    for ev in responder_eventos(modelo, tok, config, historico, **gen_kw):
        if ev["t"] == "resp":
            resposta += ev["d"]
        elif ev["t"] == "tool":
            passos.append((ev["nome"], ev["args"], ev["res"]))
    return resposta.strip(), passos or None


def responder_stream(modelo, tok, config, historico, **gen_kw):
    """Eu mostro o mesmo fluxo ao vivo no terminal: raciocínio em cinza, tool em amarelo e resposta em ciano."""
    abre = {"think": "\033[2m💭 ", "resp": "\033[96mADA>\033[0m "}
    resposta, passos, atual = "", [], None
    for ev in responder_eventos(modelo, tok, config, historico, **gen_kw):
        if ev["t"] in abre:
            if ev["t"] != atual:
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
