"""
Chat interativo com a ADA no terminal.

Carrega o Qwen3.5-9B (base) + o adapter LoRA da ADA (1_modelo/ada_v6_9b)
e mantém a conversa com histórico (multi-turn). Digite 'sair' pra encerrar.

Rodar, da raiz do projeto:
    .venv/bin/python 3_chat/chat_ada.py
"""
import os
import sys
from pathlib import Path

from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.trainer.utils import apply_lora_layers

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "5_conhecimento"))
from conhecimento import carregar_conhecimento  # base de fatos confiáveis
sys.path.insert(0, str(RAIZ / "6_assistente"))
import cerebro_tools as ct  # runtime de tools: gera, executa a tool se houver, devolve a resposta

MODELO = "mlx-community/Qwen3.5-9B-MLX-4bit"
# ADA_ADAPTER escolhe a versão (default v6_9b, o 9B treiwnado na nuvem); ADA_ADAPTER=ada_v5 volta pro antigo
ADAPTER = str(RAIZ / "1_modelo" / os.environ.get("ADA_ADAPTER", "ada_v9_9b"))
_BASE = "" if os.environ.get("ADA_BASE", "on") == "off" else "\n\n" + carregar_conhecimento()
SYSTEM = "Usuário atual: Victor, seu criador. Seja direta e objetiva não invente informações."
MAX_TOKENS = 4096          # solto: nunca corta o think+resposta; teto so de seguranca (anti-loop)
TEMPERATURE = 0.5          # 9B aguenta mais solta sem virar aleatorio
TOP_P = 0.9                # corta a cauda improvavel (evita alucinacao/frase quebrada) sem ficar decorado
REPETITION_PENALTY = 1  # leve: o 9B repete bem menos que o 7B
SHOW_THINK = os.environ.get("ADA_SHOW_THINK", "off") == "on"  # demo: mostra o raciocinio (pro video)


def main():
    _b = "OFF (teste puro)" if os.environ.get("ADA_BASE", "on") == "off" else "ON"
    print(f"[ADAPTER: {Path(ADAPTER).name} | base de conhecimento: {_b}]")
    print("Carregando a ADA... (uns 30-60s)")
    model, processor = load(MODELO, processor_config={"trust_remote_code": True})
    config = model.config.__dict__
    model = apply_lora_layers(model, ADAPTER)

    print("\n" + "=" * 56)
    print("  ADA pronta. Fala com ela.  ('sair' pra encerrar)")
    print("=" * 56 + "\n")


    historico = [{"role": "system", "content": SYSTEM}]

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
        gkw = dict(max_tokens=MAX_TOKENS, temperature=TEMPERATURE, top_p=TOP_P,
                   repetition_penalty=REPETITION_PENALTY)
        if SHOW_THINK:
            # modo demo: streama o raciocinio AO VIVO (cinza) + tools + resposta ao vivo
            resposta, passo = ct.responder_stream(model, processor, config, historico, **gkw)
            print()
        else:
            resposta, passo = ct.responder(model, processor, config, historico, **gkw)
            if passo:  # chamou tool(s): mostra cada uma (nome -> resultado)
                for t_nome, _, t_res in passo:
                    print(f"\033[93m[{t_nome} → {t_res}]\033[0m")
            print(f"\033[96mADA>\033[0m {resposta}\n")
        historico.append({"role": "assistant", "content": resposta})


if __name__ == "__main__":
    main()
