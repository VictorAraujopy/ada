"""
Valida a ESCOLHA de tool, SEM executar nada (nao mexe no Mac): pra cada pedido,
mostra qual tool a ADA decidiu chamar e compara com o esperado.

    .venv/bin/python 6_assistente/testar_escolha.py
"""
import sys
from pathlib import Path

from mlx_vlm import generate
from mlx_vlm.prompt_utils import apply_chat_template

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "6_assistente"))
import cerebro  # núcleo da ADA

SYSTEM = cerebro.SYSTEM_VOZ  # mesmo system da voz

# (pedido, tool esperada)  -- None = nao deve chamar tool nenhuma
CASOS = [
    ("que horas são?", "que_horas"),
    ("como tá meu mac?", "status_mac"),
    ("abre o spotify", "abrir_app"),
    ("bota o volume em 20", "ajustar_volume"),
    ("pula essa musica", "proxima_musica"),
    ("qual a capital da frança?", None),
    ("tô meio pra baixo hoje", None),
]


def main():
    print(f"Carregando 9B + adapter {Path(cerebro.ADAPTER).name}...", flush=True)
    model, processor, config = cerebro.carregar()
    print("pronto.\n" + "=" * 60, flush=True)

    acertos = 0
    for pedido, esperado in CASOS:
        hist = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": pedido}]
        prompt = apply_chat_template(processor, config, hist, add_generation_prompt=True,
                                     num_images=0, enable_thinking=True, tools=cerebro.POOL)
        r = generate(model, processor, prompt, max_tokens=400, temperature=0.6, top_p=0.9,
                     repetition_penalty=1.05, verbose=False)
        texto = (r.text if hasattr(r, "text") else str(r)).strip()
        chamadas = cerebro.parse_tool_calls(texto)     # lista de (nome, args); [] = nenhuma tool
        escolheu = chamadas[0][0] if chamadas else None
        ok = escolheu == esperado
        acertos += ok
        print(f"[{'OK' if ok else 'XX'}] {pedido}", flush=True)
        print(f"     esperado={esperado} | escolheu={escolheu}", flush=True)

    print(f"\n>>> {acertos}/{len(CASOS)} certos", flush=True)


if __name__ == "__main__":
    main()
