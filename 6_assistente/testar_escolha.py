"""
Valida a ESCOLHA de tool, SEM executar nada (nao mexe no Mac): pra cada pedido,
mostra qual tool a ADA decidiu chamar e compara com o esperado.

    .venv/bin/python 6_assistente/testar_escolha.py
"""
import sys
from pathlib import Path

from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.trainer.utils import apply_lora_layers

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "6_assistente"))
import cerebro_tools as ct
sys.path.insert(0, str(RAIZ / "5_conhecimento"))
from conhecimento import carregar_conhecimento

MODELO = "mlx-community/Qwen3.5-9B-MLX-4bit"
ADAPTER = str(RAIZ / "1_modelo" / "ada_v6_9b")
SYSTEM = ("Usuário atual: Victor, seu criador. Você responde por voz, então vá direto ao "
          "ponto. Se o pedido pede uma ferramenta (hora, status, app, música...), use a "
          "ferramenta — você não tem relógio nem sensores próprios.\n\n"
          + carregar_conhecimento())  # = nova proposta de system da voz

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
    print("Carregando 9B + adapter v6...", flush=True)
    model, processor = load(MODELO, processor_config={"trust_remote_code": True})
    config = model.config.__dict__
    model = apply_lora_layers(model, ADAPTER)
    print("pronto.\n" + "=" * 60, flush=True)

    acertos = 0
    for pedido, esperado in CASOS:
        hist = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": pedido}]
        prompt = apply_chat_template(processor, config, hist, add_generation_prompt=True,
                                     num_images=0, enable_thinking=True, tools=ct.POOL)
        r = generate(model, processor, prompt, max_tokens=400, temperature=0.6, top_p=0.9,
                     repetition_penalty=1.05, verbose=False)
        texto = (r.text if hasattr(r, "text") else str(r)).strip()
        chamadas = ct.parse_tool_calls(texto)          # lista de (nome, args); [] = nenhuma tool
        escolheu = chamadas[0][0] if chamadas else None
        ok = escolheu == esperado
        acertos += ok
        print(f"[{'OK' if ok else 'XX'}] {pedido}", flush=True)
        print(f"     esperado={esperado} | escolheu={escolheu}", flush=True)

    print(f"\n>>> {acertos}/{len(CASOS)} certos", flush=True)


if __name__ == "__main__":
    main()
