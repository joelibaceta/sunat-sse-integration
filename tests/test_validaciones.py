from datetime import date
from decimal import Decimal

import pytest

from sunat_see import (
    Boleta,
    Cliente,
    Credito,
    Cuota,
    Factura,
    Item,
    NotaCredito,
    Referencia,
    ValidacionError,
)


def test_factura_requiere_cliente_con_ruc(factura):
    factura.cliente = Cliente.con_dni("45678912", "JUAN PEREZ")
    with pytest.raises(ValidacionError, match="requiere cliente con RUC"):
        factura.validar()


def test_serie_de_factura_debe_empezar_con_f(factura):
    factura.serie = "B001"
    with pytest.raises(ValidacionError, match="Serie de factura inválida"):
        factura.validar()


def test_boleta_sin_documento_hasta_700(emisor):
    boleta = Boleta(
        serie="B001", numero=1, emisor=emisor,
        cliente=Cliente.publico_general(),
        items=[Item("Producto caro", 1, precio=Decimal("800.00"))],
    )
    with pytest.raises(ValidacionError, match="requiere identificar al comprador"):
        boleta.validar()


def test_cuotas_deben_sumar_el_total(factura):
    factura.forma_pago = Credito([
        Cuota(monto=Decimal("1000.00"), vencimiento=date(2026, 11, 15)),
        Cuota(monto=Decimal("1000.00"), vencimiento=date(2026, 12, 15)),
    ])
    with pytest.raises(ValidacionError, match="no coincide con el total"):
        factura.validar()


def test_cuotas_correctas_validan(factura):
    factura.forma_pago = Credito([
        Cuota(monto=Decimal("1000.00"), vencimiento=date(2026, 11, 15)),
        Cuota(monto=Decimal("1419.00"), vencimiento=date(2026, 12, 15)),
    ])
    factura.validar()


def test_cuota_no_puede_vencer_antes_de_emision(factura):
    factura.forma_pago = Credito([
        Cuota(monto=Decimal("2419.00"), vencimiento=date(2026, 10, 1)),
    ])
    with pytest.raises(ValidacionError, match="posterior a la emisión"):
        factura.validar()


def test_item_requiere_precio_o_valor():
    with pytest.raises(ValidacionError, match="exactamente uno"):
        Item("Sin importe", 1)
    with pytest.raises(ValidacionError, match="exactamente uno"):
        Item("Ambos", 1, precio=10, valor=10)


def test_nota_credito_serie_coherente_con_referencia(emisor, cliente_ruc):
    nc = NotaCredito(
        serie="BC01", numero=1, emisor=emisor, cliente=cliente_ruc,
        afecta=Referencia("01", "F001", 123),
        items=[Item("Devolución", 1, precio="10.00")],
    )
    with pytest.raises(ValidacionError, match="debe empezar con 'F'"):
        nc.validar()


def test_nota_credito_desde_factura(factura):
    nc = NotaCredito(
        serie="FC01", numero=1, emisor=factura.emisor, cliente=factura.cliente,
        afecta=factura, motivo="06",
        items=factura.items,
    )
    nc.validar()
    assert nc.referencia.full_id == "F001-123"
    assert nc.sustento == "Devolucion total"


def test_dni_invalido():
    with pytest.raises(ValidacionError, match="DNI inválido"):
        Cliente.con_dni("123", "X")
