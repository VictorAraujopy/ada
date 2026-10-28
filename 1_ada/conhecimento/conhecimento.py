"""RAG"""
from pathlib import Path
import os
import torch
import requests 
import sqlite3
import json
import re
import time
from sentence_transformers import SentenceTransformer
import numpy as np
PASTA_DOS_PROJETOS = Path(__file__).resolve().parents[3]
DB = Path(os.environ.get("ADA_DB") or PASTA_DOS_PROJETOS / "ada-api" / "dados" / "conversas.db")
model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", device="cpu")
BASE = Path(__file__).resolve().parent / "base" / "enciclopedia.db"
ENDERECO_DO_EMBEDDING, CHAVE_DO_EMBEDDING = None, None
try:
    from privado_local import ENDERECO_DO_EMBEDDING, CHAVE_DO_EMBEDDING
except ImportError:
    pass
PREFIXO_DA_PERGUNTA = "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"


def vetor_no_pc(pergunta):
    """Pede ao servidor do PC (Qwen3-Embedding-4B) o vetor da pergunta; devolve None se o PC não responder."""
    if not ENDERECO_DO_EMBEDDING:
        return None
    try:
        resposta = requests.post(f"http://{ENDERECO_DO_EMBEDDING}/v1/embeddings",
                                 json={"input": PREFIXO_DA_PERGUNTA + pergunta},
                                 headers={"Authorization": f"Bearer {CHAVE_DO_EMBEDDING}"}, timeout=10)
        resposta.raise_for_status()
    except requests.RequestException:
        return None
    return np.array(resposta.json()["data"][0]["embedding"], dtype=np.float32)

def montar(historico, k_wiki=5, k_chats=2, corte=1000, nota_minima_wiki=0.55, nota_minima_wiki_4b=0.60,
           nota_minima_chats=0.60):
    """Devolve uma cópia do histórico com a última mensagem do user trocada pelo bloco do RAG: wiki, conversas passadas e a mensagem atual."""
    ultima = historico[-1]
    if ultima["role"] != "user":
        return list(historico)

    pergunta = ultima["content"]
    if isinstance(ultima["content"], list):
        pergunta = ""
        for parte in ultima["content"]:
            if parte["type"] == "text":
                pergunta = parte["text"]
    if not pergunta:
        return list(historico)

    texto_da_busca = pergunta
    penultima = historico[-2] if len(historico) >= 2 else None
    if penultima and penultima["role"] == "assistant" and isinstance(penultima["content"], str):
        texto_da_busca = penultima["content"] + "\n" + pergunta

    vetor_da_pergunta = model.encode(texto_da_busca, prompt_name="query", normalize_embeddings=True)
    vetor_da_wiki = vetor_da_pergunta
    if modelo_da_wiki == "4B":
        vetor_da_wiki = vetor_no_pc(texto_da_busca)
        nota_minima_wiki = nota_minima_wiki_4b

    trechos_da_wiki = []
    conn = sqlite3.connect(f"file:{BASE}?mode=ro", uri=True)
    for id_, nota in buscar(vetor_da_wiki, matriz_w, id_w, k_wiki):
        if nota < nota_minima_wiki:
            continue
        pagina, secao, texto = conn.execute("SELECT pagina, secao, texto FROM trechos WHERE rowid = ?", (id_,)).fetchone()
        titulo = f"{pagina} / {secao}" if secao else pagina
        trecho = f"{titulo}: {texto}"
        trechos_da_wiki.append(trecho[:corte])
    conn.close()

    respostas_desta_conversa = {m["content"] for m in historico if m["role"] == "assistant"}
    trechos_das_conversas = []
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    for id_, nota in buscar(vetor_da_pergunta, matriz_c, id_c, k_chats + len(respostas_desta_conversa)):
        if nota < nota_minima_chats:
            continue
        linha_da_resposta = conn.execute("SELECT conversa, content FROM mensagens WHERE n = ?", (id_,)).fetchone()
        if linha_da_resposta is None:
            continue
        conversa, resposta_antiga = linha_da_resposta
        if resposta_antiga in respostas_desta_conversa:
            continue
        pergunta_antiga = conn.execute("SELECT content FROM mensagens WHERE conversa = ? AND n < ? AND role = 'user' "
                                       "ORDER BY n DESC LIMIT 1", (conversa, id_)).fetchone()[0]
        trecho = f"user: {pergunta_antiga}\nassistant: {resposta_antiga}"
        trechos_das_conversas.append(trecho[:corte])
        if len(trechos_das_conversas) == k_chats:
            break
    conn.close()

    blocos = []
    if trechos_da_wiki:
        blocos.append("[Knowledge base — use only if relevant]\n" + "\n\n".join(trechos_da_wiki))
    if trechos_das_conversas:
        blocos.append("[Past conversations — use only if relevant]\n" + "\n\n".join(trechos_das_conversas))
    if not blocos:
        return list(historico)
    blocos.append("[Current message]\n" + pergunta)
    texto_montado = "\n\n".join(blocos)

    if isinstance(ultima["content"], str):
        nova_ultima = {**ultima, "content": texto_montado}
    else:
        partes_novas = []
        for parte in ultima["content"]:
            if parte["type"] == "text":
                partes_novas.append({**parte, "text": texto_montado})
            else:
                partes_novas.append(parte)
        nova_ultima = {**ultima, "content": partes_novas}
    return historico[:-1] + [nova_ultima]


def buscar(vetor, matriz, id, k):
    if vetor is None or matriz.shape[0] == 0:
        return []

    if matriz.dtype == np.float16:
        notas = np.concatenate([matriz[i:i + 20000].astype(np.float32) @ vetor for i in range(0, matriz.shape[0], 20000)])
    else:
        notas = matriz @ vetor

    kp = np.argsort(notas)[::-1][:k]

    resultado = []
    for pos in kp:
        resultado.append((id[pos], float(notas[pos])))
    
    return resultado
    

id_c = []
matriz_c = None
def carregar_conhecimento_chats():
    global matriz_c, id_c
        
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    cur.execute("CREATE TABLE IF NOT EXISTS vetorizado(id INTEGER PRIMARY KEY, vetor BLOB)")
        
    mi = cur.execute("SELECT id, vetor FROM vetorizado")
    mit = mi.fetchall()
        
    id_c = []    
    list_trans = []
    for id_, mib in mit:  
        id_c.append(id_)
        list_trans.append(np.frombuffer(mib, dtype=np.float32))
        
        
    if list_trans:
        matriz_c = np.vstack(list_trans)
    else:
        matriz_c = np.empty((0, 1024), dtype=np.float32)  
          
    conn.close()
    print(matriz_c.shape, len(id_c))


matriz_w = None
id_w = []
modelo_da_wiki = "0.6B"
def carregar_conhecimento_wiki():
    global matriz_w, id_w, modelo_da_wiki
    
    conn = sqlite3.connect(BASE)
    cur = conn.cursor()
    
    cur.execute("CREATE TABLE IF NOT EXISTS vetorizado(id INTEGER PRIMARY KEY, vetor BLOB)")

    tem_4b = cur.execute("SELECT name FROM sqlite_master WHERE name = 'vetorizado_4b'").fetchone()
    if tem_4b and vetor_no_pc("teste") is not None:
        modelo_da_wiki, tabela, tipo, dimensoes = "4B", "vetorizado_4b", np.float16, 2560
    else:
        modelo_da_wiki, tabela, tipo, dimensoes = "0.6B", "vetorizado", np.float32, 1024
    
    mi = cur.execute(f"SELECT id, vetor FROM {tabela}")
    mit = mi.fetchall()
    
    id_w = []
    list_trans = []
    for id_, mib in mit:
        
        id_w.append(id_)
        list_trans.append(np.frombuffer(mib, dtype=tipo))
        
    if list_trans:
        matriz_w = np.vstack(list_trans)
    else:
        matriz_w = np.empty((0, dimensoes), dtype=tipo)
        
    conn.close()
    print(modelo_da_wiki, matriz_w.shape, len(id_w))
    

def vetorizar_pmensagem(id, pergunta, resposta):
    global matriz_c, id_c, model
    
    if not pergunta or not resposta:
        return
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    juntando =(f"user: {pergunta} assistant: {resposta}")
    
    vet = model.encode(juntando, normalize_embeddings=True)
    
    matriz_c = np.vstack([matriz_c, vet])
    id_c.append(id)
    
    cur.execute("INSERT OR REPLACE INTO vetorizado (id, vetor) VALUES (?, ?)",
                (id, vet.tobytes()),)
    
    conn.commit()
    conn.close()
    


def guardar(conversa, historico, meta):
    """Grava no conversas.db a pergunta (historico[-2], user) e a resposta (historico[-1], assistant), numa transação só."""
    pergunta = historico[-2]
    resposta = historico[-1]

    texto_da_pergunta = pergunta["content"]
    nome_da_foto = None
    if isinstance(pergunta["content"], list):
        for parte in pergunta["content"]:
            if parte["type"] == "text":
                texto_da_pergunta = parte["text"]
            elif parte["type"] == "image":
                nome_da_foto = Path(parte["arquivo"]).name

    agora = time.time()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("INSERT INTO mensagens (conversa, role, content, meta, criada, foto) VALUES (?,?,?,?,?,?)",
                (conversa, "user", texto_da_pergunta, None, agora, nome_da_foto))
    cur.execute("INSERT INTO mensagens (conversa, role, content, meta, criada, foto) VALUES (?,?,?,?,?,?)",
                (conversa, "assistant", resposta["content"], json.dumps(meta, ensure_ascii=False), agora, None))
    
    id = cur.lastrowid
    
    cur.execute("UPDATE conversas SET atualizada=? WHERE id=?", (agora, conversa))

    conn.commit()
    conn.close()
    
    vetorizar_pmensagem(id, texto_da_pergunta, resposta["content"])

def vetorizar_chat():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    lm = cur.execute("SELECT n, conversa, role, content FROM mensagens ORDER BY conversa, n")
    lmt = lm.fetchall()
    
    lmtextos = []
    ids = []
    pergunta = None
    conversa_ant = None
    
    for n, conversa, role, content in lmt:
        
        if conversa_ant != conversa:
            pergunta = None
            
        conversa_ant = conversa
        
        if not content: continue
        
        elif role == "user":
            pergunta = content
        
        elif role == "assistant" and pergunta:
            lmtextos.append(f"user: {pergunta} assistant: {content}")
            ids.append(n)
            pergunta = None
    
    model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")
    vet = model.encode(lmtextos, normalize_embeddings=True)
    
    cur.execute("CREATE TABLE IF NOT EXISTS vetorizado(id INTEGER PRIMARY KEY, vetor BLOB)")
        
    for y, i in zip(ids, vet):
        cur.execute("INSERT OR REPLACE INTO vetorizado(id, vetor) VALUES(?, ?)",
                    (y, i.tobytes()),)
        
    conn.commit()
    conn.close()
   
            
def vetorizar_wiki(tamanho_do_pedaco=900):
    conn = sqlite3.connect(BASE)
    cur = conn.cursor()

    longos = cur.execute("SELECT rowid, wiki, pagina, secao, texto FROM trechos WHERE length(texto) > ?",
                         (tamanho_do_pedaco,)).fetchall()
    for rowid, wiki, pagina, secao, texto in longos:
        partes = []
        for frase in re.split(r"(?<=[.!?])\s+|\n+", texto):
            if len(frase) > tamanho_do_pedaco:
                partes.extend(frase.split(" "))
            else:
                partes.append(frase)

        pedacos = []
        pedaco = ""
        for parte in partes:
            if pedaco and len(pedaco) + 1 + len(parte) > tamanho_do_pedaco:
                pedacos.append(pedaco)
                pedaco = ""
            pedaco = f"{pedaco} {parte}".strip()
        pedacos.append(pedaco)

        cur.execute("DELETE FROM trechos WHERE rowid = ?", (rowid,))
        for pedaco in pedacos:
            cur.execute("INSERT INTO trechos (wiki, pagina, secao, texto) VALUES (?, ?, ?, ?)",
                        (wiki, pagina, secao, pedaco))
    
    lt = cur.execute("SELECT rowid, wiki, pagina, secao, texto FROM trechos")
    ltuplas = lt.fetchall()
    ltextos = [" ".join(str(campo) for campo in linhas[1:]) for linhas in ltuplas]
    ids = [linha[0] for linha in ltuplas]
    
    #carregar modelo
    model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")
    vet = model.encode(ltextos, normalize_embeddings=True)
    
    cur.execute("DROP TABLE IF EXISTS vetorizado")
    cur.execute("CREATE TABLE IF NOT EXISTS vetorizado(id INTEGER PRIMARY KEY, vetor BLOB)")
    
    for y, i in zip(ids, vet):
        cur.execute("INSERT OR REPLACE INTO vetorizado(id, vetor) VALUES(?, ?)",
                    (y, i.tobytes()),)
    
    conn.commit()
    conn.close()
        
if __name__ == "__main__":
    carregar_conhecimento_wiki()
    