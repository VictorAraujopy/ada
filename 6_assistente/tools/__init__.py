"""
Pacote das ferramentas reais da ADA. Junta as tools de cada categoria num unico
dicionario EXECUTORES (nome-da-tool -> funcao), que o runtime (cerebro_tools) usa
pra achar e rodar a funcao certa.

Adicionar tool nova:
  1. escreva a funcao no modulo da categoria certa (ex: sistema.py)
  2. registre ela no EXEC daquele modulo
  pronto — ela entra aqui automaticamente, sem re-treinar o modelo.
"""
from . import sistema, apps, musica, arquivos, lembretes

EXECUTORES = {
    **sistema.EXEC,
    **apps.EXEC,
    **musica.EXEC,
    **arquivos.EXEC,
    **lembretes.EXEC,
}
