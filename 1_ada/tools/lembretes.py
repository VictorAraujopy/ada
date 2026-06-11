"""
Tools de LEMBRETES (app Lembretes do Mac) + a destrutiva esvaziar_lixeira (desarmada).
"""
from ._base import osa


def criar_lembrete(texto=None, quando=None, **kw):
    if not texto:
        return "faltou o texto"
    osa(f'tell application "Reminders" to make new reminder with properties {{name:"{texto}"}}')
    return f"lembrete criado: {texto}" + (f" ({quando})" if quando else "")


def listar_lembretes(**kw):
    r = osa('tell application "Reminders" to get name of reminders whose completed is false')
    nomes = [n.strip() for n in r.split(",") if n.strip()]
    return "lembretes: " + ("; ".join(nomes[:10]) if nomes else "nenhum ativo")


def definir_alarme(hora=None, **kw):
    if not hora:
        return "faltou a hora"
    osa(f'tell application "Reminders" to make new reminder with properties {{name:"Alarme {hora}"}}')
    return f"alarme pra {hora} (criado como lembrete)"


def esvaziar_lixeira(**kw):
    # DESARMADA: apaga arquivos de verdade. So liberar quando o runtime tiver confirmacao.
    return "esvaziar a lixeira ainda nao ta liberado (acao destrutiva, falta a confirmacao)"


EXEC = {
    "criar_lembrete": criar_lembrete, "listar_lembretes": listar_lembretes,
    "definir_alarme": definir_alarme, "esvaziar_lixeira": esvaziar_lixeira,
}
