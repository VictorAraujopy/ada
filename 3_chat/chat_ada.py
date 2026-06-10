"""
Chat interativo com a ADA no terminal.

Carrega o cérebro (Qwen3.5-9B + adapter LoRA) via 6_assistente/cerebro.py e mantém
a conversa com histórico (multi-turn). Digite 'sair' pra encerrar.

Rodar, da raiz do projeto:
    .venv/bin/python 3_chat/chat_ada.py
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "6_assistente"))
import cerebro  # núcleo da ADA: config, system, carregar, runtime de tools

SHOW_THINK = os.environ.get("ADA_SHOW_THINK", "off") == "on"  # demo: mostra o raciocinio (pro video)


def main():
    _b = "OFF (teste puro)" if os.environ.get("ADA_BASE", "on") == "off" else "ON"
    print(f"[ADAPTER: {Path(cerebro.ADAPTER).name} | base de conhecimento: {_b}]")
    print("Carregando a ADA... (uns 30-60s)")
    model, processor, config = cerebro.carregar()

    print("\n" + "=" * 56)
    print("  ADA pronta. Fala com ela.  ('sair' pra encerrar)")
    print("=" * 56 + "\n")

    historico = [{"role": "system", "content": cerebro.SYSTEM}]

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
            # modo demo: streama o raciocinio AO VIVO (cinza) + tools + resposta ao vivo
            resposta, passo = cerebro.responder_stream(model, processor, config, historico, **cerebro.GEN)
            print()
        else:
            resposta, passo = cerebro.responder(model, processor, config, historico, **cerebro.GEN)
            if passo:  # chamou tool(s): mostra cada uma (nome -> resultado)
                for t_nome, _, t_res in passo:
                    print(f"\033[93m[{t_nome} → {t_res}]\033[0m")
            print(f"\033[96mADA>\033[0m {resposta}\n")
        historico.append({"role": "assistant", "content": resposta})


if __name__ == "__main__":
    main()
