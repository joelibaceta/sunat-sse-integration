"""Catálogos SUNAT usados por el SDK (subconjunto práctico).

Referencia: anexos de la R.S. 097-2012/SUNAT y sus modificatorias
(``urn:pe:gob:sunat:cpe:see:gem:catalogos``).
"""
from __future__ import annotations

from enum import Enum


class TipoComprobante(str, Enum):
    """Catálogo 01 — tipo de comprobante de pago."""

    FACTURA = "01"
    BOLETA = "03"
    NOTA_CREDITO = "07"
    NOTA_DEBITO = "08"


class TipoDocIdentidad(str, Enum):
    """Catálogo 06 — tipo de documento de identidad."""

    SIN_DOCUMENTO = "0"
    DNI = "1"
    CARNET_EXTRANJERIA = "4"
    RUC = "6"
    PASAPORTE = "7"


class Afectacion(str, Enum):
    """Catálogo 07 — afectación del IGV (operaciones onerosas).

    Las operaciones gratuitas (11–16, 21, 31–36) no están soportadas en esta
    versión del SDK.
    """

    GRAVADO = "10"
    EXONERADO = "20"
    INAFECTO = "30"
    EXPORTACION = "40"


class Unidad(str, Enum):
    """Catálogo 03 — unidades de medida (subconjunto usual, UN/ECE rec 20)."""

    UNIDAD = "NIU"
    SERVICIO = "ZZ"
    KILOGRAMO = "KGM"
    GRAMO = "GRM"
    LITRO = "LTR"
    METRO = "MTR"
    METRO_CUADRADO = "MTK"
    CAJA = "BX"
    PAQUETE = "PK"
    DOCENA = "DZN"
    GALON = "GLL"


class MotivoNotaCredito(str, Enum):
    """Catálogo 09 — tipo de nota de crédito."""

    ANULACION_DE_LA_OPERACION = "01"
    ANULACION_POR_ERROR_EN_RUC = "02"
    CORRECCION_POR_ERROR_EN_DESCRIPCION = "03"
    DESCUENTO_GLOBAL = "04"
    DESCUENTO_POR_ITEM = "05"
    DEVOLUCION_TOTAL = "06"
    DEVOLUCION_POR_ITEM = "07"
    BONIFICACION = "08"
    DISMINUCION_EN_EL_VALOR = "09"
    OTROS_CONCEPTOS = "10"
    AJUSTES_DE_EXPORTACION = "11"
    AJUSTES_AFECTOS_AL_IVAP = "12"
    AJUSTES_MONTOS_O_FECHAS_DE_PAGO = "13"

    @property
    def descripcion(self) -> str:
        return _DESC_NOTA_CREDITO[self.value]


_DESC_NOTA_CREDITO = {
    "01": "Anulacion de la operacion",
    "02": "Anulacion por error en el RUC",
    "03": "Correccion por error en la descripcion",
    "04": "Descuento global",
    "05": "Descuento por item",
    "06": "Devolucion total",
    "07": "Devolucion por item",
    "08": "Bonificacion",
    "09": "Disminucion en el valor",
    "10": "Otros conceptos",
    "11": "Ajustes de operaciones de exportacion",
    "12": "Ajustes afectos al IVAP",
    "13": "Ajustes - montos y/o fechas de pago",
}


class MotivoNotaDebito(str, Enum):
    """Catálogo 10 — tipo de nota de débito."""

    INTERESES_POR_MORA = "01"
    AUMENTO_EN_EL_VALOR = "02"
    PENALIDADES = "03"
    AJUSTES_DE_EXPORTACION = "11"
    AJUSTES_AFECTOS_AL_IVAP = "12"

    @property
    def descripcion(self) -> str:
        return _DESC_NOTA_DEBITO[self.value]


_DESC_NOTA_DEBITO = {
    "01": "Intereses por mora",
    "02": "Aumento en el valor",
    "03": "Penalidades / otros conceptos",
    "11": "Ajustes de operaciones de exportacion",
    "12": "Ajustes afectos al IVAP",
}
