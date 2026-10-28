"""Vetoriza os trechos da wiki com o Qwen3-Embedding-4B numa GPU do Modal e grava na tabela vetorizado_4b do enciclopedia.db local (float16), sem tocar na vetorizado do 0.6B (modal run 1_ada/conhecimento/base/vetorizar_modal_4b.py)."""
import sqlite3
from pathlib import Path

import modal

app = modal.App("ada-vetorizar-wiki-4b")

BANCO_LOCAL = Path("1_ada/conhecimento/base/enciclopedia.db")
PERGUNTAS_DE_TESTE = ["how did glenn die in the comic?", "who is ada wong?", "tell me about the spencer mansion",
                      "whats your favorite food?"]

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.12.0",
        "transformers==5.9.0",
        "sentence-transformers==6.2.0",
        "numpy",
    )
    .add_local_file(str(BANCO_LOCAL), remote_path="/raiz/enciclopedia.db")
)


@app.function(image=image, gpu="B200", memory=32 * 1024, timeout=60 * 60)
def vetorizar():
    """Lê os trechos com o mesmo texto do vetorizar_wiki (wiki pagina secao texto), vetoriza no 4B e devolve os ids, os vetores e as perguntas de teste."""
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    conn = sqlite3.connect("/raiz/enciclopedia.db")
    linhas = conn.execute("SELECT rowid, wiki, pagina, secao, texto FROM trechos").fetchall()
    conn.close()
    ids = [linha[0] for linha in linhas]
    textos = [" ".join(str(campo) for campo in linha[1:]) for linha in linhas]

    modelo = SentenceTransformer("Qwen/Qwen3-Embedding-4B", device="cuda", model_kwargs={"torch_dtype": torch.bfloat16})
    modelo.max_seq_length = 1024
    vetores = modelo.encode(textos, batch_size=128, normalize_embeddings=True, show_progress_bar=True)
    perguntas = modelo.encode(PERGUNTAS_DE_TESTE, prompt_name="query", normalize_embeddings=True)
    return ids, vetores.astype(np.float16).tobytes(), perguntas.astype(np.float32).tobytes()


@app.local_entrypoint()
def main():
    """Grava os vetores na vetorizado_4b do banco local e guarda as perguntas de teste pra comparar com o servidor do PC."""
    import numpy as np

    ids, vetores_em_bytes, perguntas_em_bytes = vetorizar.remote()
    vetores = np.frombuffer(vetores_em_bytes, dtype=np.float16).reshape(len(ids), -1)
    conn = sqlite3.connect(BANCO_LOCAL)
    conn.execute("DROP TABLE IF EXISTS vetorizado_4b")
    conn.execute("CREATE TABLE vetorizado_4b(id INTEGER PRIMARY KEY, vetor BLOB)")
    conn.executemany("INSERT INTO vetorizado_4b(id, vetor) VALUES(?, ?)",
                     ((id_, vetor.tobytes()) for id_, vetor in zip(ids, vetores)))
    conn.commit()
    conn.close()
    perguntas = np.frombuffer(perguntas_em_bytes, dtype=np.float32).reshape(len(PERGUNTAS_DE_TESTE), -1)
    np.save("1_ada/conhecimento/base/perguntas_de_teste_4b.npy", perguntas)
    print(f">>> OK: {len(ids)} vetores de {vetores.shape[1]} dimensões na vetorizado_4b")
