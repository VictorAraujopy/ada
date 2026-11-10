"""Cérebro da ADA: configura, carrega o modelo e o mmproj, e responde em eventos (raciocínio, tools e resposta)."""
import atexit
import ctypes
import json
import os
import re
import socket
import sys
from dataclasses import dataclass, replace
from itertools import chain
from pathlib import Path

import llama_cpp
import llama_cpp.mtmd_cpp as mtmd
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer

RAIZ = Path(__file__).resolve().parents[2]
PASTA_DOS_MODELOS = Path.home() / "Desktop" / "ada"
sys.path.insert(0, str(RAIZ / "1_ada"))

from cerebro.memoria import Modelo
from conhecimento.conhecimento import carregar_conhecimento_chats, montar
from tools import EXECUTORES
from visao import olho

ENDERECO_DO_PC = None
try:
    from privado_local import ENDERECO_DO_PC
except ImportError:
    pass

FIM_THINK, TOOL = "</think>", "<tool_call>"
INICIO_DA_CONVERSA, INICIO_DA_RESPOSTA = "<|im_start|>user", "<|im_start|>assistant"


@dataclass(frozen=True)
class Config:
    """Configuração de um processo: modelo, mmproj, contexto, sampling, tools, o system e a divisão com o PC."""

    adapter: str
    pasta_adapter: Path | None
    adapter_com_o_pc: str | None
    servidor_rpc: str | None
    fracao_no_pc: float
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
    system: str
    vagas_de_memoria: int


def configurar():
    """Monta o Config a partir do ADA_ADAPTER, do ADA_RPC (ou do endereço do PC no privado_local) e do tools_pool.json."""
    adapter_escolhido = os.environ.get("ADA_ADAPTER")
    nome_adapter = "ada_1_0_2_27b" if adapter_escolhido is None else adapter_escolhido
    return Config(
        adapter=nome_adapter or "qwen3.8_27b_cru",
        pasta_adapter=PASTA_DOS_MODELOS / nome_adapter if nome_adapter else None,
        adapter_com_o_pc="ada_1_0_3_27b_iq4_xs" if adapter_escolhido is None else None,
        servidor_rpc=os.environ.get("ADA_RPC", ENDERECO_DO_PC) or None,
        fracao_no_pc=0.33,
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
        system="Current user: Victor.",
        vagas_de_memoria=4,
    )


def carregar(config=None):
    """Abre o GGUF com todas as camadas na GPU (dividido com o PC quando ele responde), o mmproj, o tokenizer do Qwen e os vetores do RAG das conversas, e já guarda o começo fixo (system + tools) na memória; devolve (modelo, tokenizer, config)."""
    config = _com_o_pc_se_der(config or configurar())
    gguf, lora = _arquivos_do_modelo(config)
    divisao_entre_pc_e_mac = None
    if config.servidor_rpc:
        divisao_entre_pc_e_mac = [config.fracao_no_pc, 1 - config.fracao_no_pc]
    modelo = Modelo(config.vagas_de_memoria, model_path=gguf, n_ctx=config.n_ctx,
                    n_gpu_layers=-1, flash_attn=True, n_ubatch=config.n_ubatch, lora_path=lora,
                    tensor_split=divisao_entre_pc_e_mac, use_mmap=not config.servidor_rpc, verbose=False)
    atexit.register(modelo.close)
    modelo.olho = olho.abrir_o_olho(modelo, config)
    atexit.register(mtmd.mtmd_free, modelo.olho)
    tok = AutoTokenizer.from_pretrained(config.tokenizer)
    _guardar_o_comeco_fixo(modelo, tok, config)
    carregar_conhecimento_chats()
    return modelo, tok, config


def _com_o_pc_se_der(config):
    """Troca pra ADA de 4 bits dividida com o PC se ela existe e o ggml-rpc-server responde; senão fica no adapter do Config, só no Mac."""
    if not config.servidor_rpc or not config.adapter_com_o_pc:
        return replace(config, servidor_rpc=None)
    pasta_com_o_pc = PASTA_DOS_MODELOS / config.adapter_com_o_pc
    if not (pasta_com_o_pc / "ada.gguf").exists():
        return replace(config, servidor_rpc=None)
    if not _registrar_o_pc(config.servidor_rpc):
        print(f"o PC ({config.servidor_rpc}) não respondeu: rodando a {config.adapter} só no Mac")
        return replace(config, servidor_rpc=None)
    return replace(config, adapter=config.adapter_com_o_pc, pasta_adapter=pasta_com_o_pc)


def _registrar_o_pc(endereco):
    """Registra o ggml-rpc-server do PC como mais um dispositivo do llama.cpp (ele recebe as primeiras camadas); devolve se deu certo."""
    if not llama_cpp.llama_supports_rpc():
        return False
    host, porta = endereco.rsplit(":", 1)
    try:
        socket.create_connection((host, int(porta)), timeout=3).close()
    except OSError:
        return False
    lib_do_llama = llama_cpp.llama_cpp._lib
    lib_do_llama.ggml_backend_rpc_add_server.argtypes = [ctypes.c_char_p]
    lib_do_llama.ggml_backend_rpc_add_server.restype = ctypes.c_void_p
    lib_do_llama.ggml_backend_register.argtypes = [ctypes.c_void_p]
    registro = lib_do_llama.ggml_backend_rpc_add_server(endereco.encode())
    if not registro:
        return False
    lib_do_llama.ggml_backend_register(registro)
    return True


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


def _posicoes(tokens, procurado):
    """Devolve as posições onde a sequência `procurado` começa dentro de `tokens`."""
    tamanho = len(procurado)
    return [i for i in range(len(tokens) - tamanho + 1) if tokens[i:i + tamanho] == procurado]


def _cortar_prompt(modelo, tok, config, hist, pensando):
    """Monta o prompt pelo chat template e corta ele em texto e imagens pelo olho."""
    prompt = tok.apply_chat_template(hist, tools=config.pool, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=pensando, preserve_thinking=False)
    return olho.cortar_prompt(modelo, prompt, olho.arquivos_das_imagens(hist))


def _guardar_o_comeco_fixo(modelo, tok, config):
    """Lê o system + tools de uma conversa vazia e guarda na memória, pra primeira mensagem de qualquer conversa já retomar dele."""
    conversa_vazia = [{"role": "system", "content": config.system}, {"role": "user", "content": ""}]
    cortado = _cortar_prompt(modelo, tok, config, conversa_vazia, pensando=True)
    try:
        inicio_da_conversa = modelo.tokenize(INICIO_DA_CONVERSA.encode(), add_bos=False, special=True)
        comeco_fixo = _posicoes(cortado.tokens, inicio_da_conversa)[0]
        olho.ler_ate(modelo, cortado, comeco_fixo)
        modelo.guardar(cortado.tokens[:comeco_fixo])
    finally:
        mtmd.mtmd_input_chunks_free(cortado.pedacos)


def _gerar(modelo, tok, config, hist, pensando, gen_kw):
    """Monta o prompt pelo chat template, retoma da maior memória guardada, guarda o começo fixo, o começo e o fim da pergunta e gera o texto em stream."""
    cortado = _cortar_prompt(modelo, tok, config, hist, pensando)
    try:
        inicio_da_conversa = modelo.tokenize(INICIO_DA_CONVERSA.encode(), add_bos=False, special=True)
        inicio_da_resposta = modelo.tokenize(INICIO_DA_RESPOSTA.encode(), add_bos=False, special=True)
        comeco_fixo = _posicoes(cortado.tokens, inicio_da_conversa)[:1]
        antes_da_pergunta = _posicoes(cortado.tokens, inicio_da_conversa)[-1:]
        ate_a_pergunta = _posicoes(cortado.tokens, inicio_da_resposta)[-1:]
        paradas = comeco_fixo + antes_da_pergunta + ate_a_pergunta

        lidos = modelo.retomar(cortado.tokens)
        for parada in paradas:
            if lidos < parada:
                olho.ler_ate(modelo, cortado, parada)
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
    rhis = montar(historico)
    saida = yield from _falar(modelo, tok, config, rhis, gen_kw)
    chamadas = parse_tool_calls(saida)
    if chamadas:
        respostas = []
        for nome, args in chamadas:
            resultado = executar(nome, args)
            yield {"t": "tool", "nome": nome, "args": args, "res": str(resultado)}
            respostas.append(f"<tool_response>\n{resultado}\n</tool_response>")
        hist2 = rhis + [_como_mensagem(saida), {"role": "user", "content": "\n".join(respostas)}]
        yield from _falar(modelo, tok, config, hist2, gen_kw)
    yield {"t": "fim"}

