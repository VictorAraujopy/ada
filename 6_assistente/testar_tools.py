"""
Testa o RUNTIME de tools: dado um pedido, a ADA escolhe a tool certa, executa e responde.
Mostra a tool chamada (nome + args + resultado) e a fala final da ADA.

    .venv/bin/python 6_assistente/testar_tools.py

ATENCAO: "abre o spotify" e "volume em 20" EXECUTAM de verdade (abre app, muda volume).
As outras sao leitura/inofensivas.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "6_assistente"))
import cerebro  # núcleo da ADA

SYSTEM = cerebro.SYSTEM

PEDIDOS = [
    "bom dia, ada",                # CONVERSA -> ver se o tom continua bom com thinking ON
    "que horas são?",              # tool leitura (inofensiva)
    "como tá meu mac?",            # tool leitura (inofensiva)
    "to pensando em largar a facul",  # CONVERSA -> tom/profundidade
    "qual a capital da frança?",   # NAO e tool -> responde direto
]


def main():
    print(f"Carregando 9B + adapter {Path(cerebro.ADAPTER).name}...")
    model, processor, config = cerebro.carregar()
    print("pronto.\n" + "=" * 60, flush=True)

    for p in PEDIDOS:
        hist = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": p}]
        resp, passo = cerebro.responder(model, processor, config, hist,
                                        max_tokens=256, temperature=0.6, top_p=0.9,
                                        repetition_penalty=1.05)
        print(f"VOCE> {p}", flush=True)
        if passo:
            for nome, args, resultado in passo:   # passo e uma LISTA (a ADA pode chamar varias tools)
                print(f"  \033[93m[tool: {nome}({args}) -> {resultado}]\033[0m", flush=True)
        print(f"\033[96mADA>\033[0m  {resp}\n" + "-" * 60, flush=True)


if __name__ == "__main__":
    main()
