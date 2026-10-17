"""Jerarquía de errores del SDK."""
from __future__ import annotations


class SunatError(Exception):
    """Error base de ``sunat-see``."""


class ValidacionError(SunatError):
    """El comprobante no cumple una regla de SUNAT (se detecta antes de enviar)."""


class SoapFault(SunatError):
    """Fault SOAP devuelto por el servicio de SUNAT (código + mensaje)."""

    def __init__(self, codigo: str, mensaje: str):
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(f"[{codigo}] {mensaje}")


class RespuestaInvalida(SunatError):
    """La respuesta de SUNAT no tiene la estructura esperada."""
