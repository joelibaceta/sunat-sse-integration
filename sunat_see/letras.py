"""Conversión de importes a letras para la leyenda 1000 de SUNAT.

Ejemplo: ``Decimal("1419.00")`` → ``"MIL CUATROCIENTOS DIECINUEVE CON 00/100 SOLES"``.
Se escribe en mayúsculas y sin tildes, como es usual en la representación impresa.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_UNIDADES = ("", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE")
_DIEZ_A_QUINCE = ("DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE")
_DECENAS = ("", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA")
_CENTENAS = ("", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
             "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS")

_MONEDAS = {"PEN": "SOLES", "USD": "DOLARES AMERICANOS", "EUR": "EUROS"}


def _hasta_99(n: int, apocope: bool) -> str:
    if n == 1:
        return "UN" if apocope else "UNO"
    if n <= 9:
        return _UNIDADES[n]
    if n <= 15:
        return _DIEZ_A_QUINCE[n - 10]
    if n <= 19:
        return "DIECI" + _UNIDADES[n - 10]
    if n == 20:
        return "VEINTE"
    if n <= 29:
        return "VEINTI" + _hasta_99(n - 20, apocope)
    d, u = divmod(n, 10)
    palabra = _DECENAS[d]
    if u:
        palabra += " Y " + _hasta_99(u, apocope)
    return palabra


def _hasta_999(n: int, apocope: bool) -> str:
    if n == 100:
        return "CIEN"
    c, r = divmod(n, 100)
    partes = []
    if c:
        partes.append(_CENTENAS[c])
    if r:
        partes.append(_hasta_99(r, apocope))
    return " ".join(partes)


def _hasta_999999(n: int, apocope: bool) -> str:
    miles, resto = divmod(n, 1000)
    partes = []
    if miles == 1:
        partes.append("MIL")
    elif miles:
        partes.append(_hasta_999(miles, apocope=True) + " MIL")
    if resto:
        partes.append(_hasta_999(resto, apocope))
    return " ".join(partes)


def numero_a_letras(n: int) -> str:
    """Convierte un entero (0 – 999 999 999 999) a letras en español."""
    if n < 0:
        raise ValueError("solo se admiten números no negativos")
    if n == 0:
        return "CERO"
    millones, resto = divmod(n, 1_000_000)
    partes = []
    if millones == 1:
        partes.append("UN MILLON")
    elif millones:
        partes.append(_hasta_999999(millones, apocope=True) + " MILLONES")
    if resto:
        partes.append(_hasta_999999(resto, apocope=False))
    return " ".join(partes)


def monto_en_letras(monto: Decimal, moneda: str = "PEN") -> str:
    """Formatea un importe como leyenda SUNAT (código 1000)."""
    m = Decimal(monto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entero = int(m)
    centimos = int((m - entero) * 100)
    nombre = _MONEDAS.get(moneda, moneda)
    return f"{numero_a_letras(entero)} CON {centimos:02d}/100 {nombre}"
