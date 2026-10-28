"""RAG"""
from pathlib import Path
import os
import requests 
import sqlite3
import json
import time
import numpy as np
PASTA_DOS_PROJETOS = Path(__file__).resolve().parents[3]
DB = Path(os.environ.get("ADA_DB") or PASTA_DOS_PROJETOS / "ada-api" / "dados" / "conversas.db")
ENDERECO_DO_EMBEDDING, CHAVE_DO_EMBEDDING = None, None
try:
    from privado_local import ENDERECO_DO_EMBEDDING, CHAVE_DO_EMBEDDING
except ImportError:
    pass
PREFIXO_DA_PERGUNTA = "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"


def vetor_no_pc(texto, tempo_maximo=10):
    """Pede ao servidor do PC (Qwen3-Embedding-4B) o vetor do texto; devolve None se o PC não responder em `tempo_maximo` segundos."""
    if not ENDERECO_DO_EMBEDDING:
        return None
    try:
        resposta = requests.post(f"http://{ENDERECO_DO_EMBEDDING}/v1/embeddings",
                                 json={"input": texto},
                                 headers={"Authorization": f"Bearer {CHAVE_DO_EMBEDDING}"}, timeout=tempo_maximo)
        resposta.raise_for_status()
    except requests.RequestException:
        return None
    return np.array(resposta.json()["data"][0]["embedding"], dtype=np.float32)

def montar(historico, k_chats=2, corte=1000, nota_minima_chats=0.60):
    """Devolve uma cópia do histórico com a última mensagem do user trocada pelo bloco do RAG: conversas passadas e a mensagem atual."""
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

    vetor_da_pergunta = vetor_no_pc(PREFIXO_DA_PERGUNTA + texto_da_busca)

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

    if not trechos_das_conversas:
        return list(historico)
    texto_montado = ("[Past conversations — use only if relevant]\n" + "\n\n".join(trechos_das_conversas)
                     + "\n\n[Current message]\n" + pergunta)

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
        matriz_c = np.empty((0, 2560), dtype=np.float32)
          
    conn.close()
    print(matriz_c.shape, len(id_c))


def vetorizar_pmensagem(id, pergunta, resposta):
    global matriz_c, id_c
    
    if not pergunta or not resposta:
        return
    
    juntando =(f"user: {pergunta} assistant: {resposta}")

    vet = vetor_no_pc(juntando, tempo_maximo=60)
    if vet is None:
        return

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
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
    """Apaga a vetorizado do conversas.db e vetoriza de novo todos os pares pergunta/resposta no servidor do PC."""
    if vetor_no_pc("teste") is None:
        print("o servidor de embedding do PC não respondeu: nada foi mexido")
        return

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
    
    cur.execute("DROP TABLE IF EXISTS vetorizado")
    cur.execute("CREATE TABLE vetorizado(id INTEGER PRIMARY KEY, vetor BLOB)")
    
    vetorizados = 0
    for y, texto in zip(ids, lmtextos):
        vet = vetor_no_pc(texto, tempo_maximo=60)
        if vet is None:
            print(f"sem vetor: resposta {y}")
            continue
        cur.execute("INSERT INTO vetorizado(id, vetor) VALUES(?, ?)",
                    (y, vet.tobytes()),)
        vetorizados += 1
        
    conn.commit()
    conn.close()
    print(f"{vetorizados} de {len(ids)} pares vetorizados no 4B")
   
            
if __name__ == "__main__":
    carregar_conhecimento_chats()
