"""Bloques declarativos con los que se arman los comprobantes.

Todos los importes se manejan con ``Decimal``; se aceptan ``int``/``str``/``float``
y se convierten en el constructor (``float`` pasa por ``str`` para evitar ruido
binario).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from .catalogs import Afectacion, TipoDocIdentidad, Unidad
from .exceptions import ValidacionError

Numero = Decimal | int | str | float


def _dec(valor: Numero, campo: str) -> Decimal:
    try:
        return Decimal(str(valor))
    except InvalidOperation as exc:
        raise ValidacionError(f"{campo}: '{valor}' no es un número válido") from exc


@dataclass(frozen=True)
class Emisor:
    """Contribuyente que emite el comprobante."""

    ruc: str
    razon_social: str
    nombre_comercial: str = ""
    direccion: str = ""
    ubigeo: str = ""
    codigo_local: str = "0000"  # código de establecimiento anexo (0000 = principal)

    def __post_init__(self):
        if not re.fullmatch(r"\d{11}", self.ruc):
            raise ValidacionError(f"RUC del emisor inválido: '{self.ruc}' (deben ser 11 dígitos)")


@dataclass(frozen=True)
class Cliente:
    """Adquirente. Usa los constructores ``con_ruc``/``con_dni``/... según el caso."""

    tipo_doc: str
    numero_doc: str
    nombre: str
    direccion: str = ""

    @classmethod
    def con_ruc(cls, ruc: str, razon_social: str, direccion: str = "") -> "Cliente":
        if not re.fullmatch(r"\d{11}", ruc):
            raise ValidacionError(f"RUC del cliente inválido: '{ruc}' (deben ser 11 dígitos)")
        return cls(TipoDocIdentidad.RUC.value, ruc, razon_social, direccion)

    @classmethod
    def con_dni(cls, dni: str, nombre: str, direccion: str = "") -> "Cliente":
        if not re.fullmatch(r"\d{8}", dni):
            raise ValidacionError(f"DNI inválido: '{dni}' (deben ser 8 dígitos)")
        return cls(TipoDocIdentidad.DNI.value, dni, nombre, direccion)

    @classmethod
    def con_carnet_extranjeria(cls, numero: str, nombre: str, direccion: str = "") -> "Cliente":
        return cls(TipoDocIdentidad.CARNET_EXTRANJERIA.value, numero, nombre, direccion)

    @classmethod
    def con_pasaporte(cls, numero: str, nombre: str, direccion: str = "") -> "Cliente":
        return cls(TipoDocIdentidad.PASAPORTE.value, numero, nombre, direccion)

    @classmethod
    def publico_general(cls, nombre: str = "CLIENTES VARIOS") -> "Cliente":
        """Consumidor final sin documento (solo boletas, hasta S/ 700)."""
        return cls(TipoDocIdentidad.SIN_DOCUMENTO.value, "-", nombre)


@dataclass(frozen=True)
class Item:
    """Línea del comprobante.

    Indica el importe unitario de UNA de dos formas:

    - ``precio``: precio de venta unitario, **con IGV incluido** (lo que paga el
      cliente). El SDK calcula el valor neto hacia atrás.
    - ``valor``: valor unitario **sin IGV**.

    Para ítems exonerados/inafectos/exportación no hay IGV, así que ambos
    equivalen.
    """

    descripcion: str
    cantidad: Numero
    precio: Numero | None = field(default=None, kw_only=True)
    valor: Numero | None = field(default=None, kw_only=True)
    unidad: str = field(default=Unidad.UNIDAD.value, kw_only=True)
    afectacion: Afectacion = field(default=Afectacion.GRAVADO, kw_only=True)
    codigo: str = field(default="", kw_only=True)  # código interno del producto (opcional)

    def __post_init__(self):
        if not self.descripcion.strip():
            raise ValidacionError("Item: la descripción no puede estar vacía")
        if (self.precio is None) == (self.valor is None):
            raise ValidacionError(
                f"Item '{self.descripcion}': indica exactamente uno de 'precio' (con IGV) o 'valor' (sin IGV)"
            )
        object.__setattr__(self, "cantidad", _dec(self.cantidad, "cantidad"))
        if self.cantidad <= 0:
            raise ValidacionError(f"Item '{self.descripcion}': la cantidad debe ser mayor que 0")
        for campo in ("precio", "valor"):
            v = getattr(self, campo)
            if v is not None:
                v = _dec(v, campo)
                if v < 0:
                    raise ValidacionError(f"Item '{self.descripcion}': {campo} no puede ser negativo")
                object.__setattr__(self, campo, v)
        object.__setattr__(self, "afectacion", Afectacion(self.afectacion))
        object.__setattr__(self, "unidad", str(self.unidad))

    def valor_unitario(self, tasa_igv: Decimal) -> Decimal:
        """Valor unitario sin IGV (precisión completa, sin redondear)."""
        if self.valor is not None:
            return self.valor
        if self.afectacion is Afectacion.GRAVADO:
            return self.precio / (Decimal("1") + tasa_igv)
        return self.precio

    def precio_unitario(self, tasa_igv: Decimal) -> Decimal:
        """Precio de venta unitario con IGV (si aplica)."""
        if self.precio is not None:
            return self.precio
        if self.afectacion is Afectacion.GRAVADO:
            return self.valor * (Decimal("1") + tasa_igv)
        return self.valor


# --- Formas de pago (R.S. 193-2020/SUNAT) ------------------------------------


@dataclass(frozen=True)
class Contado:
    """Venta al contado (forma de pago por defecto)."""


@dataclass(frozen=True)
class Cuota:
    monto: Numero
    vencimiento: date

    def __post_init__(self):
        object.__setattr__(self, "monto", _dec(self.monto, "monto de cuota"))
        if self.monto <= 0:
            raise ValidacionError("Cuota: el monto debe ser mayor que 0")


@dataclass(frozen=True)
class Credito:
    """Venta al crédito: la suma de las cuotas debe igualar el total del comprobante."""

    cuotas: tuple[Cuota, ...]

    def __init__(self, cuotas):
        object.__setattr__(self, "cuotas", tuple(cuotas))
        if not self.cuotas:
            raise ValidacionError("Credito: se requiere al menos una cuota")

    @property
    def monto_pendiente(self) -> Decimal:
        return sum((c.monto for c in self.cuotas), Decimal("0"))


@dataclass(frozen=True)
class Referencia:
    """Documento afectado por una nota de crédito/débito, cuando no se tiene el
    objeto original a la mano: ``Referencia("01", "F001", 123)``."""

    tipo: str    # "01" factura, "03" boleta
    serie: str
    numero: int

    def __post_init__(self):
        if self.tipo not in ("01", "03"):
            raise ValidacionError(f"Referencia: tipo '{self.tipo}' no válido (01=factura, 03=boleta)")

    @property
    def full_id(self) -> str:
        return f"{self.serie}-{self.numero}"
