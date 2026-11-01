"""Chat de terminal com a ADA, pra debugar o cérebro: .venv/bin/python 3_chat/chat_ada.py"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "1_ada"))
from cerebro import cerebro

SHOW_THINK = os.environ.get("ADA_SHOW_THINK", "off") == "on"


def responder(modelo, tok, config, historico, **gen_kw):
    """Roda o responder_eventos do cérebro e junta o resultado em (resposta, passos das tools)."""
    resposta, passos = "", []
    for evento in cerebro.responder_eventos(modelo, tok, config, historico, **gen_kw):
        if evento["t"] == "resp":
            resposta += evento["d"]
        elif evento["t"] == "tool":
            passos.append((evento["nome"], evento["args"], evento["res"]))
    return resposta.strip(), passos or None


def responder_stream(modelo, tok, config, historico, **gen_kw):
    """Roda o responder_eventos do cérebro imprimindo ao vivo no terminal (raciocínio em cinza, tool em amarelo, resposta em ciano) e devolve (resposta, passos)."""
    abre = {"think": "\033[2m💭 ", "resp": "\033[96mADA>\033[0m "}
    resposta, passos, atual = "", [], None
    for evento in cerebro.responder_eventos(modelo, tok, config, historico, **gen_kw):
        if evento["t"] in abre:
            if evento["t"] != atual:
                print(("\033[0m\n" if atual else "") + abre[evento["t"]], end="", flush=True)
                atual = evento["t"]
            print(evento["d"], end="", flush=True)
            if evento["t"] == "resp":
                resposta += evento["d"]
        elif evento["t"] == "tool":
            print(("\033[0m\n" if atual else "") + f"\033[93m[{evento['nome']} → {evento['res']}]\033[0m")
            passos.append((evento["nome"], evento["args"], evento["res"]))
            atual = None
    print("\033[0m")
    return resposta.strip(), passos or None


def main():
    """Carrega a ADA e conversa no terminal até 'sair'."""
    config = cerebro.configurar()
    print(f"[ADAPTER: {config.adapter}]")
    print("Carregando a ADA... (uns 30-60s)")
    model, processor, config = cerebro.carregar(config)

    print("\n" + "=" * 56)
    print("  ADA pronta. Fala com ela.  ('sair' pra encerrar)")
    print("=" * 56 + "\n")

    historico = [{"role": "system", "content": config.system}]

    while True:
        try:
            entrada = input("\033[1mvocê>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté, Victor.")
            break

        if entrada.lower() in ("sair", "exit", "quit"):
            print("Até, Victor.")
            break
        if not entrada:
            continue

        historico.append({"role": "user", "content": entrada})
        if SHOW_THINK:
            resposta, passo = responder_stream(model, processor, config, historico, **config.geracao)
            print()
        else:
            resposta, passo = responder(model, processor, config, historico, **config.geracao)
            if passo:
                for t_nome, _, t_res in passo:
                    print(f"\033[93m[{t_nome} → {t_res}]\033[0m")
            print(f"\033[96mADA>\033[0m {resposta}\n")
        historico.append({"role": "assistant", "content": resposta})


if __name__ == "__main__":
    main()
