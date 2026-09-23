from ._base import osa


def criar_lembrete(texto=None, quando=None, **kw):
    if not texto:
        return "missing the text"
    osa(f'tell application "Reminders" to make new reminder with properties {{name:"{texto}"}}')
    return f"reminder created: {texto}" + (f" ({quando})" if quando else "")


def listar_lembretes(**kw):
    r = osa('tell application "Reminders" to get name of reminders whose completed is false')
    nomes = [n.strip() for n in r.split(",") if n.strip()]
    return "reminders: " + ("; ".join(nomes[:10]) if nomes else "no active reminders")


def definir_alarme(hora=None, **kw):
    if not hora:
        return "missing the time"
    osa(f'tell application "Reminders" to make new reminder with properties {{name:"Alarme {hora}"}}')
    return f"alarm set for {hora} (created as a reminder)"


def esvaziar_lixeira(**kw):
    # DESARMADA: apaga arquivos de verdade. So liberar quando o runtime tiver confirmacao.
    return "emptying the trash isn't enabled yet (destructive action, confirmation step missing)"


EXEC = {
    "criar_lembrete": criar_lembrete, "listar_lembretes": listar_lembretes,
    "definir_alarme": definir_alarme, "esvaziar_lixeira": esvaziar_lixeira,
}
