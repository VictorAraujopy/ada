"""Cérebro da ADA: configura, carrega o modelo e o mmproj, e responde em eventos (raciocínio, tools e resposta)."""
import atexit
import ctypes
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

import llama_cpp
import llama_cpp.mtmd_cpp as mtmd
from huggingface_hub import hf_hub_download
from llama_cpp import Llama
from transformers import AutoTokenizer

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "1_ada"))
from tools import EXECUTORES

FIM_THINK, TOOL = "</think>", "<tool_call>"
INICIO_DA_CONVERSA, INICIO_DA_RESPOSTA = "<|im_start|>user", "<|im_start|>assistant"
IMAGEM_NO_TEMPLATE = "<|vision_start|><|image_pad|><|vision_end|>"


@dataclass(frozen=True)
class Config:
    """Configuração de um processo: modelo, mmproj, contexto, sampling, tools e o system de cada usuário."""

    adapter: str
    pasta_adapter: Path | None
    repo_base: str
    arquivo_base: str
    repo_olho: str
    arquivo_olho: str
    threads_do_olho: int
    tokenizer: str
    n_ctx: int
    n_ubatch: int
    geracao: dict
    pool: list
    systems: dict
    pasta_memorias: Path
    maximo_memorias: int


def configurar():
    """Monta o Config a partir do ADA_ADAPTER, do tools_pool.json e das personas."""
    nome_adapter = os.environ.get("ADA_ADAPTER", "ada_1_0_27b")
    persona_visitante = "Current user: visitor (not Victor, not your creator). Be kind, don't make things up."
    return Config(
        adapter=nome_adapter or "qwen3.8_27b_cru",
        pasta_adapter=RAIZ / "_modelo" / nome_adapter if nome_adapter else None,
        repo_base="ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF",
        arquivo_base="Qwen3.8-27B-GSQ-RCO-IQ3_XXS.gguf",
        repo_olho="bartowski/Qwen3.8-27B-GGUF",
        arquivo_olho="mmproj-Qwen3.8-27B-f16.gguf",
        threads_do_olho=8,
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
    """Devolve a PERSONA_CONVIDADO do personas_local.py (fora do git), ou `padrao` se o arquivo não existir."""
    try:
        from personas_local import PERSONA_CONVIDADO
    except ImportError:
        return padrao
    return PERSONA_CONVIDADO


class Modelo(Llama):
    """Llama que salva o estado do llama.cpp em disco e retoma do maior começo de prompt já lido, em vez de reler tudo."""

    def __init__(self, pasta_memorias, maximo_memorias, **kwargs):
        """Abre o modelo, cria a pasta de memórias deste processo e apaga as de processos que já acabaram."""
        super().__init__(**kwargs)
        _apagar_memorias_de_processos_mortos(pasta_memorias)
        self.pasta_memorias = pasta_memorias / str(os.getpid())
        self.pasta_memorias.mkdir(parents=True, exist_ok=True)
        atexit.register(shutil.rmtree, self.pasta_memorias, True)
        self.maximo_memorias = maximo_memorias
        self.memorias = {}
        self.continuar = False
        self.olho = None

    def generate(self, tokens, **kwargs):
        """Gera a partir do estado carregado quando `continuar` está ligado, sem tentar reaproveitar o prefixo."""
        if self.continuar:
            kwargs["reset"] = False
        return super().generate(tokens, **kwargs)

    def retomar(self, tokens):
        """Carrega a memória salva que cobre o maior começo de `tokens` e devolve quantos tokens ela já leu (0 se nenhuma cobre)."""
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
        """Salva em disco o estado que leu exatamente `tokens` e apaga a memória menos usada se passar de `maximo_memorias`."""
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
    """Apaga as pastas de memória cujo PID não está mais rodando."""
    for pasta in raiz.glob("*"):
        try:
            os.kill(int(pasta.name), 0)
        except (ValueError, ProcessLookupError):
            shutil.rmtree(pasta, ignore_errors=True)
        except PermissionError:
            pass


def carregar(config=None):
    """Abre o GGUF com todas as camadas na GPU, o mmproj e o tokenizer do Qwen; devolve (modelo, tokenizer, config)."""
    config = config or configurar()
    gguf, lora = _arquivos_do_modelo(config)
    modelo = Modelo(config.pasta_memorias, config.maximo_memorias, model_path=gguf, n_ctx=config.n_ctx,
                    n_gpu_layers=-1, flash_attn=True, n_ubatch=config.n_ubatch, lora_path=lora, verbose=False)
    atexit.register(modelo.close)
    modelo.olho = _abrir_o_olho(modelo, config)
    atexit.register(mtmd.mtmd_free, modelo.olho)
    tok = AutoTokenizer.from_pretrained(config.tokenizer)
    return modelo, tok, config


def _abrir_o_olho(modelo, config):
    """Abre o mmproj F16 do Qwen3.8 (visão) na CPU."""
    parametros = mtmd.mtmd_context_params_default()
    parametros.use_gpu = False
    parametros.print_timings = False
    parametros.n_threads = config.threads_do_olho
    parametros.flash_attn_type = llama_cpp.LLAMA_FLASH_ATTN_TYPE_ENABLED
    arquivo_do_olho = hf_hub_download(config.repo_olho, config.arquivo_olho)
    olho = mtmd.mtmd_init_from_file(arquivo_do_olho.encode(), modelo.model, parametros)
    if olho is None or not mtmd.mtmd_support_vision(olho):
        raise RuntimeError(f"não consegui abrir o olho em {arquivo_do_olho}")
    return olho


def _arquivos_do_modelo(config):
    """Devolve (gguf, lora): o ada.gguf fundido sem LoRA, se existir; senão o 27B da ISTA com o adapter.gguf."""
    if config.pasta_adapter and (config.pasta_adapter / "ada.gguf").exists():
        return str(config.pasta_adapter / "ada.gguf"), None
    base = hf_hub_download(config.repo_base, config.arquivo_base)
    lora = str(config.pasta_adapter / "adapter.gguf") if config.pasta_adapter else None
    return base, lora


def parse_tool_calls(texto):
    """Extrai do texto as chamadas de tool como lista de (nome, args)."""
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
    """Roda a função da tool `nome` com `args` e devolve o resultado, ou a mensagem de erro em vez de levantar exceção."""
    fn = EXECUTORES.get(nome)
    if not fn:
        return f"tool '{nome}' not implemented yet"
    try:
        return fn(**args)
    except Exception as e:
        return f"error in tool {nome}: {e}"


@dataclass
class PromptCortado:
    """Prompt tokenizado: os tokens em ordem, as imagens por posição, o total de células no contexto e os pedaços do mtmd."""

    tokens: list
    imagens: dict
    celulas: int
    pedacos: object


def _cortar_prompt(modelo, prompt, arquivos_das_imagens):
    """Divide o prompt em pedaços de texto e de imagem pelo mtmd; cada imagem ocupa as posições dela com uma marca tirada do hash da foto."""
    marcador = mtmd.mtmd_default_marker().decode()
    texto = prompt.replace(IMAGEM_NO_TEMPLATE, marcador).encode("utf-8")
    bitmaps = [_abrir_a_foto(modelo.olho, arquivo) for arquivo in arquivos_das_imagens]
    entrada = mtmd.mtmd_input_text()
    entrada.text = texto
    entrada.text_len = len(texto)
    entrada.add_special = True
    entrada.parse_special = True
    pedacos = mtmd.mtmd_input_chunks_init()
    lista_de_bitmaps = (mtmd.mtmd_bitmap_p_ctypes * len(bitmaps))(*bitmaps)
    resultado = mtmd.mtmd_tokenize(modelo.olho, pedacos, ctypes.byref(entrada), lista_de_bitmaps, len(bitmaps))
    for bitmap in bitmaps:
        mtmd.mtmd_bitmap_free(bitmap)
    if resultado != 0:
        mtmd.mtmd_input_chunks_free(pedacos)
        raise ValueError(f"não consegui cortar o prompt com {len(bitmaps)} imagem(ns) (erro {resultado} do mtmd)")

    tokens, imagens, celulas_a_mais = [], {}, 0
    for i in range(mtmd.mtmd_input_chunks_size(pedacos)):
        pedaco = mtmd.mtmd_input_chunks_get(pedacos, i)
        if mtmd.mtmd_input_chunk_get_type(pedaco) == mtmd.MTMD_INPUT_CHUNK_TYPE_TEXT:
            tokens += _tokens_do_texto(pedaco)
            continue
        imagens[len(tokens)] = pedaco
        marca_da_foto = -1 - int(mtmd.mtmd_input_chunk_get_id(pedaco)[:7], 16)
        posicoes = mtmd.mtmd_input_chunk_get_n_pos(pedaco)
        tokens += [marca_da_foto] * posicoes
        celulas_a_mais += mtmd.mtmd_input_chunk_get_n_tokens(pedaco) - posicoes
    return PromptCortado(tokens=tokens, imagens=imagens, celulas=len(tokens) + celulas_a_mais, pedacos=pedacos)


def _abrir_a_foto(olho, arquivo):
    """Abre a imagem como bitmap do mtmd com o sha256 dos bytes como id, pra memória reconhecer a mesma foto."""
    bitmap = mtmd.mtmd_helper_bitmap_init_from_file(olho, str(arquivo).encode(), False)
    if bitmap is None:
        raise ValueError(f"não consegui abrir a imagem {arquivo}")
    identidade = hashlib.sha256(Path(arquivo).read_bytes()).hexdigest()
    mtmd.mtmd_bitmap_set_id(bitmap, identidade.encode())
    return bitmap


def _tokens_do_texto(pedaco):
    """Devolve os tokens de um pedaço de texto do mtmd."""
    quantos = ctypes.c_size_t()
    ponteiro = mtmd.mtmd_input_chunk_get_tokens_text(pedaco, ctypes.byref(quantos))
    return [ponteiro[i] for i in range(quantos.value)]


def _arquivos_das_imagens(hist):
    """Lista o arquivo de cada imagem do histórico, na ordem em que o template escreve."""
    return [parte["arquivo"] for mensagem in hist if isinstance(mensagem["content"], list)
            for parte in mensagem["content"] if parte.get("type") == "image"]


def _posicoes(tokens, procurado):
    """Devolve as posições onde a sequência `procurado` começa dentro de `tokens`."""
    tamanho = len(procurado)
    return [i for i in range(len(tokens) - tamanho + 1) if tokens[i:i + tamanho] == procurado]


def _ler_ate(modelo, cortado, fim):
    """Avalia o prompt da posição atual do modelo até `fim`: texto pelo eval, imagem pelo mmproj."""
    while modelo.n_tokens < fim:
        inicio = modelo.n_tokens
        if inicio in cortado.imagens:
            _ler_imagem(modelo, cortado.imagens[inicio])
            continue
        proxima_imagem = min([posicao for posicao in cortado.imagens if posicao > inicio], default=fim)
        modelo.eval(cortado.tokens[inicio:min(fim, proxima_imagem)])


def _ler_imagem(modelo, pedaco):
    """Codifica a imagem pelo mmproj e escreve o resultado no contexto do modelo, na posição dela no prompt."""
    nova_posicao = llama_cpp.llama_pos(0)
    resultado = mtmd.mtmd_helper_eval_chunk_single(modelo.olho, modelo._ctx.ctx, pedaco, modelo.n_tokens, 0,
                                                   modelo.n_batch, False, ctypes.byref(nova_posicao))
    if resultado != 0:
        raise RuntimeError(f"a imagem não entrou no modelo (erro {resultado} do llama.cpp)")
    modelo.n_tokens = nova_posicao.value


def _gerar(modelo, tok, config, hist, pensando, gen_kw):
    """Monta o prompt pelo chat template, retoma da maior memória salva, salva o começo fixo e o fim da pergunta e gera o texto em stream."""
    prompt = tok.apply_chat_template(hist, tools=config.pool, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=pensando, preserve_thinking=False)
    cortado = _cortar_prompt(modelo, prompt, _arquivos_das_imagens(hist))
    try:
        inicio_da_conversa = modelo.tokenize(INICIO_DA_CONVERSA.encode(), add_bos=False, special=True)
        inicio_da_resposta = modelo.tokenize(INICIO_DA_RESPOSTA.encode(), add_bos=False, special=True)
        comeco_fixo = _posicoes(cortado.tokens, inicio_da_conversa)[:1]
        ate_a_pergunta = _posicoes(cortado.tokens, inicio_da_resposta)[-1:]
        paradas = comeco_fixo + ate_a_pergunta

        lidos = modelo.retomar(cortado.tokens)
        for parada in paradas:
            if lidos < parada:
                _ler_ate(modelo, cortado, parada)
                modelo.guardar(cortado.tokens[:parada])
                lidos = parada
    finally:
        mtmd.mtmd_input_chunks_free(cortado.pedacos)

    espaco = config.n_ctx - cortado.celulas
    geracao = {**gen_kw, "max_tokens": min(gen_kw.get("max_tokens", espaco), espaco)}
    modelo.continuar = True
    try:
        for pedaco in modelo(cortado.tokens[lidos:], stream=True, **geracao):
            yield pedaco["choices"][0]["text"]
    finally:
        modelo.continuar = False


def _seguro(texto, marcas):
    """Segura o final do texto quando ele pode ser o começo de uma tag que ainda não chegou inteira."""
    for n in range(min(len(texto), max(map(len, marcas)) - 1), 0, -1):
        if any(m.startswith(texto[-n:]) for m in marcas):
            return texto[:-n]
    return texto


def _partes(buf, pensando, final=False):
    """Divide o texto gerado em (raciocínio, resposta, se o raciocínio fechou); a resposta é cortada no <tool_call>."""
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
    """Gera uma vez e solta eventos 'think' até o </think> e 'resp' depois dele; no fim devolve o texto cru inteiro."""
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
    """Gera com raciocínio; se o raciocínio estourar o max_tokens sem fechar, gera de novo sem raciocínio."""
    saida = yield from _fases(modelo, tok, config, hist, True, gen_kw)
    if not _partes(saida, True, final=True)[2]:
        saida = yield from _fases(modelo, tok, config, hist, False, gen_kw)
    return saida


def _como_mensagem(saida):
    """Converte a saída do modelo em mensagem assistant do histórico, com o raciocínio em reasoning_content."""
    if FIM_THINK not in saida:
        return {"role": "assistant", "content": saida.strip()}
    think, resto = saida.split(FIM_THINK, 1)
    return {"role": "assistant", "content": resto.strip(), "reasoning_content": think.strip()}


def responder_eventos(modelo, tok, config, historico, **gen_kw):
    """Recebe o histórico da conversa e responde em eventos think/tool/resp/fim; se chamar tools, executa e responde de novo com o resultado."""
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
    """Roda o responder_eventos e junta o resultado em (resposta, passos das tools)."""
    resposta, passos = "", []
    for ev in responder_eventos(modelo, tok, config, historico, **gen_kw):
        if ev["t"] == "resp":
            resposta += ev["d"]
        elif ev["t"] == "tool":
            passos.append((ev["nome"], ev["args"], ev["res"]))
    return resposta.strip(), passos or None


def responder_stream(modelo, tok, config, historico, **gen_kw):
    """Roda o responder_eventos imprimindo ao vivo no terminal (raciocínio em cinza, tool em amarelo, resposta em ciano) e devolve (resposta, passos)."""
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
