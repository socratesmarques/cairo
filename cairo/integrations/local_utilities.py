"""Bounded, deterministic offline utilities; expressions never become Python code."""

import ast
import math
import operator
import re
import unicodedata


def fold(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


def number(value):
    if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?", value.strip()):
        raise ValueError("Informe um número decimal; não use separadores de milhares")
    result = float(value.strip().replace(",", "."))
    if not math.isfinite(result) or abs(result) > 1e100:
        raise ValueError("Número fora do limite")
    return result


def display(value):
    return format(value, ".12g")


def calculate(expression):
    if not isinstance(expression, str) or not 1 <= len(expression.strip()) <= 200:
        raise ValueError("Use uma expressão de até 200 caracteres")
    source = expression.strip().replace(",", ".").replace("×", "*").replace("÷", "/")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, RecursionError):
        raise ValueError("Expressão inválida; use números, parênteses e operações aritméticas") from None
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("Expressão muito complexa")
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                  ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            value = node.value
        elif isinstance(node, ast.UnaryOp) and type(node.op) in {ast.UAdd, ast.USub}:
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("Expoente limitado a 12")
            value = operations[type(node.op)](left, right)
        else:
            raise ValueError("Use apenas números e operações; funções e código não são aceitos")
        if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError("Resultado fora do limite real")
        return value

    try:
        result = visit(tree.body)
    except (ZeroDivisionError, OverflowError):
        raise ValueError("Divisão por zero ou resultado fora do limite") from None
    return {"value": result, "message": f"{expression.strip()} = {display(result)}"}


# Factors convert into the dimension's base unit. Data units are bytes, not bits.
UNITS = {}
for dimension, factors in {
    "length": {"m": 1, "km": 1000, "cm": .01, "mm": .001, "mi": 1609.344, "ft": .3048, "in": .0254},
    "mass": {"kg": 1, "g": .001, "mg": .000001, "lb": .45359237, "oz": .028349523125},
    "volume": {"l": 1, "ml": .001, "m3": 1000},
    "duration": {"s": 1, "min": 60, "h": 3600, "dia": 86400},
    "speed": {"m/s": 1, "km/h": 1/3.6, "mph": .44704},
    "data": {"b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3, "tb": 1000**4, "kib": 1024, "mib": 1024**2, "gib": 1024**3},
}.items():
    UNITS.update({unit: (dimension, factor) for unit, factor in factors.items()})
ALIASES = {"metros": "m", "metro": "m", "quilometros": "km", "quilometro": "km", "gramas": "g", "grama": "g", "quilos": "kg", "quilo": "kg", "quilogramas": "kg", "litros": "l", "litro": "l", "segundos": "s", "segundo": "s", "minutos": "min", "minuto": "min", "horas": "h", "hora": "h", "dias": "dia", "celsius": "c", "fahrenheit": "f", "kelvin": "k", "bytes": "b", "byte": "b"}


def convert(value, source, target):
    amount = number(value)
    if not all(isinstance(unit, str) and 0 < len(unit) <= 40 for unit in (source, target)):
        raise ValueError("Unidade inválida")
    def unit_name(unit):
        name = fold(unit.strip()).replace("°", "")
        return ALIASES.get(name, name)
    start, end = unit_name(source), unit_name(target)
    if start in {"c", "f", "k"} and end in {"c", "f", "k"}:
        kelvin = amount if start == "k" else amount + 273.15 if start == "c" else (amount - 32) * 5/9 + 273.15
        if kelvin < -1e-9:
            raise ValueError("Temperatura abaixo do zero absoluto")
        result = kelvin if end == "k" else kelvin - 273.15 if end == "c" else (kelvin - 273.15)*9/5 + 32
    elif start in UNITS and end in UNITS and UNITS[start][0] == UNITS[end][0]:
        result = amount * UNITS[start][1] / UNITS[end][1]
    else:
        raise ValueError("Unidades desconhecidas ou incompatíveis; consulte os exemplos no painel")
    if not math.isfinite(result) or abs(result) > 1e100:
        raise ValueError("Conversão fora do limite")
    return {"value": result, "source": start, "target": end, "message": f"{value} {source} = {display(result)} {target}"}


def transform(text, action):
    if not isinstance(text, str) or len(text) > 16000:
        raise ValueError("Texto limitado a 16000 caracteres")
    lines = text.splitlines()
    if action == "stats":
        words = len(re.findall(r"\b\w+\b", text, re.UNICODE))
        result = {"characters": len(text), "characters_no_spaces": sum(not c.isspace() for c in text), "words": words, "lines": len(lines), "reading_seconds": math.ceil(words / 200 * 60)}
        return {**result, "message": f"{words} palavras · {len(text)} caracteres · {len(lines)} linhas · leitura estimada: {result['reading_seconds']} s"}
    actions = {"uppercase": str.upper, "lowercase": str.lower, "title": str.title,
               "trim": lambda value: "\n".join(line.strip() for line in value.strip().splitlines()),
               "slug": lambda value: re.sub(r"[^a-z0-9]+", "-", fold(value)).strip("-"),
               "unique_lines": lambda _: "\n".join(dict.fromkeys(lines)),
               "sort_lines": lambda _: "\n".join(sorted(lines, key=fold))}
    if action not in actions:
        raise ValueError("Operação de texto desconhecida")
    result = actions[action](text)
    return {"text": result, "message": result or "Texto vazio."}
