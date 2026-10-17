from datetime import date
from decimal import Decimal

import pytest

from sunat_see import Boleta, Cliente, Emisor, Factura, Item


@pytest.fixture
def emisor():
    return Emisor(
        ruc="20123456789",
        razon_social="MI EMPRESA S.A.C.",
        nombre_comercial="Mi Tienda",
        direccion="Av. Siempre Viva 123, Lima",
        ubigeo="150101",
    )


@pytest.fixture
def cliente_ruc():
    return Cliente.con_ruc("20600055519", "CLIENTE S.A.C.")


@pytest.fixture
def factura(emisor, cliente_ruc):
    return Factura(
        serie="F001",
        numero=123,
        emisor=emisor,
        cliente=cliente_ruc,
        fecha_emision=date(2026, 10, 16),
        items=[
            Item("Laptop 14 pulgadas", 2, precio=Decimal("1180.00")),
            Item("Mouse inalámbrico", 1, precio=Decimal("59.00")),
        ],
    )


@pytest.fixture
def boleta(emisor):
    return Boleta(
        serie="B001",
        numero=45,
        emisor=emisor,
        cliente=Cliente.con_dni("45678912", "JUAN PEREZ"),
        fecha_emision=date(2026, 10, 16),
        items=[Item("Menú del día", 1, precio="15.00")],
    )
