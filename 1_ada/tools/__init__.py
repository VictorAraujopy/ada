"""As tools da ADA por categoria e o EXECUTORES, que liga o nome de cada uma à função real."""
from . import apps, web, calculo

EXECUTORES = {
    **apps.EXEC,
    **web.EXEC,
    **calculo.EXEC,
}
