#!/bin/bash
# Roda o benchmark completo nas duas ADAs e deixa tudo pronto pro julgamento do raciocínio.
#
#     bash 6_benchmark/rodar_comparacao.sh
#
# Ou desgrudado do terminal (pode fechar a janela, continua rodando):
#     nohup bash 6_benchmark/rodar_comparacao.sh > /tmp/bench.log 2>&1 &
#     tail -f /tmp/bench.log          # acompanhar
#
# ~2h30 a ADA nova (27B, inglês) + ~1h a antiga (9B, português, congelada em old/).
# Um modelo de cada vez: 16GB não aguentam os dois. Caiu no meio? Roda de novo: retoma de onde parou.
# caffeinate impede o Mac de dormir no meio.

set -e
cd "$(dirname "$0")/.."

echo "=== 1/3 — ADA nova: v12_1_en · Qwen3.8-27B · inglês ==="
caffeinate -i .venv/bin/python 6_benchmark/rodar_benchmark.py

echo "=== 2/3 — ADA antiga: v12 · Qwen3.5-9B · português (old/) ==="
caffeinate -i env ADA_ADAPTER=ada_v12_a16_9b_fp32 .venv/bin/python old/benchmark.py

echo "=== 3/3 — pontuando as objetivas ==="
.venv/bin/python 6_benchmark/pontuar_benchmark.py \
    bench_ada_v12_a16_9b_fp32.json bench_ada_v12_1_en_a16_27b.json

echo
echo "PRONTO. Falta só o julgamento do raciocínio:"
echo "  1. preencher 6_benchmark/resultados/julgamento_cego_ia.md (vencedor: 1 | 2 | empate)"
echo "  2. .venv/bin/python 6_benchmark/gerar_grafico.py"
