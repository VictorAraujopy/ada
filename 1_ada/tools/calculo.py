"""Tool de cálculo: faz a conta que o modelo erraria de cabeça, lendo a expressão pelo ast (nunca eval)."""
import ast
import math
import operator

OPERACOES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
SINAIS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCOES = {
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "log2": math.log2, "exp": math.exp,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
}
CONSTANTES = {"pi": math.pi, "e": math.e}

MAIOR_EXPOENTE = 1000
MAIOR_EXPRESSAO = 300


def _valor(no):
    """Calcula um pedaço da expressão; o que não for número, conta, função ou constante da lista é recusado."""
    if isinstance(no, ast.Constant) and type(no.value) in (int, float):
        return no.value
    if isinstance(no, ast.BinOp) and type(no.op) in OPERACOES:
        esquerda = _valor(no.left)
        direita = _valor(no.right)
        if isinstance(no.op, ast.Pow) and abs(direita) > MAIOR_EXPOENTE:
            raise ValueError("exponent too large")
        return OPERACOES[type(no.op)](esquerda, direita)
    if isinstance(no, ast.UnaryOp) and type(no.op) in SINAIS:
        return SINAIS[type(no.op)](_valor(no.operand))
    if isinstance(no, ast.Name) and no.id in CONSTANTES:
        return CONSTANTES[no.id]
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in FUNCOES and not no.keywords:
        argumentos = [_valor(argumento) for argumento in no.args]
        return FUNCOES[no.func.id](*argumentos)
    raise ValueError(f"not allowed: {ast.unparse(no)}")


def _formatar(numero):
    """Inteiro sai inteiro; quebrado sai com 12 algarismos, o que some com o lixo do ponto flutuante (0.1+0.2 = 0.3)."""
    if isinstance(numero, int):
        return str(numero) if abs(numero) < 10**15 else f"{numero:.6e}"
    return f"{numero:.12g}"


def calcular(expressao=None, **kw):
    """Faz a conta e devolve 'expressão = resultado', ou o motivo de não ter feito."""
    if not expressao or len(str(expressao)) > MAIOR_EXPRESSAO:
        return f"invalid expression: {expressao!r}"
    texto_da_conta = str(expressao).replace("^", "**").replace("×", "*").replace("÷", "/")
    try:
        arvore = ast.parse(texto_da_conta, mode="eval")
        resultado = _valor(arvore.body)
        if isinstance(resultado, complex):
            return f"{expressao}: no real result"
        return f"{expressao} = {_formatar(resultado)}"
    except ZeroDivisionError:
        return f"{expressao}: division by zero"
    except OverflowError:
        return f"{expressao}: result too large"
    except (SyntaxError, ValueError, TypeError) as erro:
        return f"invalid expression {expressao!r}: {erro}"


EXEC = {"calcular": calcular}
