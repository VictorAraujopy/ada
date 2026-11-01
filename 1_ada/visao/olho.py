"""O olho da ADA: abre o mmproj do Qwen3.8 na CPU, corta o prompt em texto e imagens pelo mtmd do llama.cpp e lê cada pedaço no contexto do modelo."""
import ctypes
import hashlib
from dataclasses import dataclass
from pathlib import Path

import llama_cpp
import llama_cpp.mtmd_cpp as mtmd
from huggingface_hub import hf_hub_download

IMAGEM_NO_TEMPLATE = "<|vision_start|><|image_pad|><|vision_end|>"


def abrir_o_olho(modelo, config):
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


@dataclass
class PromptCortado:
    """Prompt tokenizado: os tokens em ordem, as imagens por posição, o total de células no contexto e os pedaços do mtmd."""

    tokens: list
    imagens: dict
    celulas: int
    pedacos: object


def cortar_prompt(modelo, prompt, arquivos_das_imagens):
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


def arquivos_das_imagens(hist):
    """Lista o arquivo de cada imagem do histórico, na ordem em que o template escreve."""
    return [parte["arquivo"] for mensagem in hist if isinstance(mensagem["content"], list)
            for parte in mensagem["content"] if parte.get("type") == "image"]


def ler_ate(modelo, cortado, fim):
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
