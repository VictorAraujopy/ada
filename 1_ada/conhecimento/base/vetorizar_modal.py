"""Roda o vetorizar_wiki numa GPU do Modal e traz o enciclopedia.db vetorizado de volta (modal run 1_ada/conhecimento/base/vetorizar_modal.py)."""
import modal

app = modal.App("ada-vetorizar-wiki")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.12.0",
        "transformers==5.9.0",
        "sentence-transformers==6.2.0",
        "numpy",
        "requests",
    )
    .add_local_file("1_ada/conhecimento/conhecimento.py", remote_path="/raiz/1_ada/conhecimento/conhecimento.py")
    .add_local_file("1_ada/conhecimento/base/enciclopedia.db", remote_path="/raiz/1_ada/conhecimento/base/enciclopedia.db")
)


@app.function(image=image, gpu="B200", memory=16 * 1024, timeout=60 * 60)
def vetorizar():
    """Chama o vetorizar_wiki do conhecimento.py e devolve o enciclopedia.db com a tabela vetorizado."""
    import sys

    sys.path.insert(0, "/raiz/1_ada/conhecimento")
    from conhecimento import BASE, vetorizar_wiki

    vetorizar_wiki()
    return BASE.read_bytes()


@app.local_entrypoint()
def main():
    """Grava o banco que voltou do Modal por cima do 1_ada/conhecimento/base/enciclopedia.db."""
    banco = vetorizar.remote()
    with open("1_ada/conhecimento/base/enciclopedia.db", "wb") as f:
        f.write(banco)
    print(f">>> OK: {len(banco) / 1e6:.0f} MB salvos em 1_ada/conhecimento/base/enciclopedia.db")
