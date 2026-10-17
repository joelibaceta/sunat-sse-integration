"""Comprobantes declarativos: Factura, Boleta, NotaCredito y NotaDebito.

Cada clase valida las reglas de su casuística (serie, tipo de documento del
cliente, cuotas, tope de boleta sin documento, etc.) y calcula los totales.
El XML se genera con ``.xml()`` o, normalmente, se deja que ``SunatClient`` lo
haga al enviar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import ClassVar, Union

from .catalogs import Afectacion, MotivoNotaCredito, MotivoNotaDebito, TipoDocIdentidad
from .exceptions import ValidacionError
from .models import Cliente, Contado, Credito, Emisor, Item, Referencia

_TWO = Decimal("0.01")

# Tope legal para boletas emitidas sin documento de identidad del comprador.
TOPE_BOLETA_SIN_DOCUMENTO = Decimal("700.00")


def _q2(v: Decimal) -> Decimal:
    return v.quantize(_TWO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineaCalculada:
    """Resultado del cálculo de una línea (importes sin redondear salvo indicación)."""

    item: Item
    valor_unitario: Decimal   # sin IGV, precisión completa
    precio_unitario: Decimal  # con IGV (si aplica), precisión completa
    valor_venta: Decimal      # valor_unitario × cantidad, redondeado a 2
    igv: Decimal              # IGV de la línea, redondeado a 2


@dataclass(frozen=True)
class Totales:
    gravado: Decimal
    exonerado: Decimal
    inafecto: Decimal
    exportacion: Decimal
    igv: Decimal
    total: Decimal

    @property
    def subtotal(self) -> Decimal:
        """Suma de valores de venta (sin IGV)."""
        return self.gravado + self.exonerado + self.inafecto + self.exportacion


@dataclass(kw_only=True)
class _Comprobante:
    serie: str
    numero: int
    emisor: Emisor
    cliente: Cliente
    items: list[Item]
    fecha_emision: date = field(default_factory=date.today)
    moneda: str = "PEN"
    igv: Decimal = Decimal("0.18")
    observaciones: list[str] = field(default_factory=list)  # cbc:Note adicionales

    tipo: ClassVar[str] = ""

    @property
    def full_id(self) -> str:
        return f"{self.serie}-{self.numero}"

    def calcular(self) -> tuple[list[LineaCalculada], Totales]:
        """Calcula líneas y totales (IGV, bases por afectación, total a pagar)."""
        lineas: list[LineaCalculada] = []
        bases: dict[Afectacion, Decimal] = {a: Decimal("0") for a in Afectacion}
        igv_total = Decimal("0")
        for item in self.items:
            vu = item.valor_unitario(self.igv)
            pu = item.precio_unitario(self.igv)
            valor_venta = _q2(vu * item.cantidad)
            igv_linea = _q2(valor_venta * self.igv) if item.afectacion is Afectacion.GRAVADO else Decimal("0.00")
            bases[item.afectacion] += valor_venta
            igv_total += igv_linea
            lineas.append(LineaCalculada(item, vu, pu, valor_venta, igv_linea))
        totales = Totales(
            gravado=_q2(bases[Afectacion.GRAVADO]),
            exonerado=_q2(bases[Afectacion.EXONERADO]),
            inafecto=_q2(bases[Afectacion.INAFECTO]),
            exportacion=_q2(bases[Afectacion.EXPORTACION]),
            igv=_q2(igv_total),
            total=_q2(sum(bases.values(), Decimal("0")) + igv_total),
        )
        return lineas, totales

    @property
    def totales(self) -> Totales:
        return self.calcular()[1]

    @property
    def total(self) -> Decimal:
        return self.totales.total

    def validar(self) -> None:
        if not (1 <= int(self.numero) <= 99_999_999):
            raise ValidacionError(f"{self.full_id}: el correlativo debe estar entre 1 y 99999999")
        if not self.items:
            raise ValidacionError(f"{self.full_id}: el comprobante no tiene ítems")
        if self.moneda not in ("PEN", "USD", "EUR"):
            raise ValidacionError(f"{self.full_id}: moneda '{self.moneda}' no soportada")

    def xml(self) -> bytes:
        """XML UBL 2.1 **sin firmar** (la firma la agrega ``SunatClient``)."""
        from . import ubl

        return ubl.build_xml(self)


FormaPago = Union[Contado, Credito]


@dataclass(kw_only=True)
class Factura(_Comprobante):
    """Factura (01). Al contado por defecto; al crédito con ``forma_pago=Credito([...])``."""

    tipo: ClassVar[str] = "01"

    forma_pago: FormaPago = field(default_factory=Contado)
    fecha_vencimiento: date | None = None
    operacion: str = "0101"  # catálogo 51 (0101 = venta interna)

    def validar(self) -> None:
        super().validar()
        if not re.fullmatch(r"F[A-Z0-9]{3}", self.serie):
            raise ValidacionError(f"Serie de factura inválida: '{self.serie}' (formato: F + 3 alfanuméricos, ej. F001)")
        if self.cliente.tipo_doc != TipoDocIdentidad.RUC.value:
            raise ValidacionError(f"{self.full_id}: una factura requiere cliente con RUC (usa Cliente.con_ruc)")
        if isinstance(self.forma_pago, Credito):
            _, tot = self.calcular()
            suma = _q2(self.forma_pago.monto_pendiente)
            if suma != tot.total:
                raise ValidacionError(
                    f"{self.full_id}: la suma de cuotas ({suma}) no coincide con el total ({tot.total})"
                )
            for i, cuota in enumerate(self.forma_pago.cuotas, start=1):
                if cuota.vencimiento <= self.fecha_emision:
                    raise ValidacionError(
                        f"{self.full_id}: la cuota {i} vence el {cuota.vencimiento}, "
                        f"debe ser posterior a la emisión ({self.fecha_emision})"
                    )


@dataclass(kw_only=True)
class Boleta(_Comprobante):
    """Boleta de venta (03). Acepta cliente con DNI/CE/pasaporte o público general."""

    tipo: ClassVar[str] = "03"

    operacion: str = "0101"

    def validar(self) -> None:
        super().validar()
        if not re.fullmatch(r"B[A-Z0-9]{3}", self.serie):
            raise ValidacionError(f"Serie de boleta inválida: '{self.serie}' (formato: B + 3 alfanuméricos, ej. B001)")
        if self.cliente.tipo_doc == TipoDocIdentidad.SIN_DOCUMENTO.value:
            _, tot = self.calcular()
            if tot.total > TOPE_BOLETA_SIN_DOCUMENTO:
                raise ValidacionError(
                    f"{self.full_id}: una boleta mayor a S/ {TOPE_BOLETA_SIN_DOCUMENTO} "
                    "requiere identificar al comprador (DNI u otro documento)"
                )


def _referencia_de(afecta: "Factura | Boleta | Referencia") -> Referencia:
    if isinstance(afecta, Referencia):
        return afecta
    if isinstance(afecta, (Factura, Boleta)):
        return Referencia(afecta.tipo, afecta.serie, int(afecta.numero))
    raise ValidacionError(f"'afecta' debe ser una Factura, Boleta o Referencia (recibido: {type(afecta).__name__})")


@dataclass(kw_only=True)
class _Nota(_Comprobante):
    afecta: Factura | Boleta | Referencia
    sustento: str = ""

    @property
    def referencia(self) -> Referencia:
        return _referencia_de(self.afecta)

    def validar(self) -> None:
        super().validar()
        ref = self.referencia
        letra = "F" if ref.tipo == "01" else "B"
        if not re.fullmatch(rf"{letra}[A-Z0-9]{{3}}", self.serie):
            raise ValidacionError(
                f"{self.full_id}: la serie de una nota sobre {'factura' if letra == 'F' else 'boleta'} "
                f"debe empezar con '{letra}' (ej. {letra}C01)"
            )
        if ref.tipo == "01" and self.cliente.tipo_doc != TipoDocIdentidad.RUC.value:
            raise ValidacionError(f"{self.full_id}: una nota sobre factura requiere cliente con RUC")


@dataclass(kw_only=True)
class NotaCredito(_Nota):
    """Nota de crédito (07): anulación, devolución, descuento, etc. (catálogo 09)."""

    tipo: ClassVar[str] = "07"

    motivo: MotivoNotaCredito | str = MotivoNotaCredito.ANULACION_DE_LA_OPERACION

    def __post_init__(self):
        self.motivo = MotivoNotaCredito(self.motivo)
        if not self.sustento:
            self.sustento = self.motivo.descripcion


@dataclass(kw_only=True)
class NotaDebito(_Nota):
    """Nota de débito (08): intereses, aumento de valor, penalidades (catálogo 10)."""

    tipo: ClassVar[str] = "08"

    motivo: MotivoNotaDebito | str = MotivoNotaDebito.AUMENTO_EN_EL_VALOR

    def __post_init__(self):
        self.motivo = MotivoNotaDebito(self.motivo)
        if not self.sustento:
            self.sustento = self.motivo.descripcion
