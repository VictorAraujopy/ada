"""Tools de temperatura: leem o Mac (macmon) e a GTX 1060 do PC (nvidia-smi pelo ssh) e devolvem os graus já com o estado, sem a ADA julgar o número."""
import json

from ._base import sh

COMANDO_DO_MACMON = ["macmon", "pipe", "--samples", "1", "--interval", "200"]

LIMITE_DO_ALERTA_NO_MAC = 80
LIMITE_DO_MUITO_QUENTE_NO_MAC = 95

ESTADO_NORMAL_NO_MAC = "normal for the Mac, nothing to worry about"
ESTADO_ALERTA_NO_MAC = "hot, but nothing serious: heavy load, worth keeping an eye on"
ESTADO_MUITO_QUENTE_NO_MAC = "very hot for the Mac: close to where the chip slows itself down to cool off, it needs a break"

HOST_DO_PC_NO_SSH_CONFIG = "nvidia"
COMANDO_DO_NVIDIA_SMI_NO_PC = [
    "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", HOST_DO_PC_NO_SSH_CONFIG,
    "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits",
]

LIMITE_DO_ALERTA_NA_1060 = 83
LIMITE_DO_MUITO_QUENTE_NA_1060 = 95

ESTADO_NORMAL_NA_1060 = "normal for the card, nothing to worry about"
ESTADO_ALERTA_NA_1060 = "hot, but nothing serious: above the card's 83 °C target, it's trimming its clock a little"
ESTADO_MUITO_QUENTE_NA_1060 = "very hot for the card: close to its 99 °C hardware slowdown, it needs a break"


def temperatura_do_mac(**kw):
    """Lê uma amostra do macmon e devolve a CPU, a GPU e o estado da mais quente das duas."""
    saida_do_macmon = sh(COMANDO_DO_MACMON)
    try:
        leitura_do_macmon = json.loads(saida_do_macmon)
    except json.JSONDecodeError:
        return f"couldn't read the temperature: {saida_do_macmon}"

    cpu = leitura_do_macmon["temp"]["cpu_temp_avg"]
    gpu = leitura_do_macmon["temp"]["gpu_temp_avg"]
    mais_quente = max(cpu, gpu)

    if mais_quente >= LIMITE_DO_MUITO_QUENTE_NO_MAC:
        estado = ESTADO_MUITO_QUENTE_NO_MAC
    elif mais_quente >= LIMITE_DO_ALERTA_NO_MAC:
        estado = ESTADO_ALERTA_NO_MAC
    else:
        estado = ESTADO_NORMAL_NO_MAC

    return f"CPU {cpu:.0f} °C, GPU {gpu:.0f} °C. State: {estado}"


def temperatura_do_pc(**kw):
    """Lê a temperatura da GTX 1060 do PC pelo nvidia-smi via ssh e devolve os graus com o estado."""
    saida_do_nvidia_smi = sh(COMANDO_DO_NVIDIA_SMI_NO_PC)
    try:
        graus = int(saida_do_nvidia_smi)
    except ValueError:
        return "couldn't read the PC's GPU temperature: the PC may be off or out of reach"

    if graus >= LIMITE_DO_MUITO_QUENTE_NA_1060:
        estado = ESTADO_MUITO_QUENTE_NA_1060
    elif graus >= LIMITE_DO_ALERTA_NA_1060:
        estado = ESTADO_ALERTA_NA_1060
    else:
        estado = ESTADO_NORMAL_NA_1060

    return f"GTX 1060 (PC): {graus} °C. State: {estado}"


EXEC = {"temperatura_do_mac": temperatura_do_mac, "temperatura_do_pc": temperatura_do_pc}
