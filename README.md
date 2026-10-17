# sunat-see

SDK **declarativo** de facturación electrónica SUNAT (Perú). Describe el
comprobante — qué se vende, a quién, cómo se paga — y el SDK hace el resto:

- Totales, IGV y bases por afectación (gravado / exonerado / inafecto / exportación).
- XML **UBL 2.1** (factura, boleta, notas de crédito y débito) y leyenda en letras.
- Firma **XAdES-BES** dentro de `ext:ExtensionContent`, como exige SUNAT.
- Envío directo al `billService` del SEE (sin OSE): `sendBill`, `sendSummary`, `getStatus`.
- Parseo del **CDR** (constancia de recepción) y contenido del **código QR**.
- Validación de casuísticas *antes* de enviar (series, RUC/DNI, cuotas, topes).

```bash
pip install sunat-see
```

> ⚠️ Versión alpha. Probada contra el ambiente **BETA** de SUNAT. Revisa el
> [alcance](#alcance-y-roadmap) antes de usar en producción.

## Inicio rápido

```python
from sunat_see import Emisor, Cliente, Item, Factura, SunatClient

emisor = Emisor(
    ruc="20123456789",
    razon_social="MI EMPRESA S.A.C.",
    direccion="Av. Siempre Viva 123, Lima",
    ubigeo="150101",
)

factura = Factura(
    serie="F001",
    numero=123,
    emisor=emisor,
    cliente=Cliente.con_ruc("20600055519", "CLIENTE S.A.C."),
    items=[
        Item("Laptop 14 pulgadas", 2, precio="1180.00"),  # precio final, con IGV
        Item("Mouse inalámbrico", 1, precio="59.00"),
    ],
)

client = SunatClient.beta(ruc="20123456789")
resultado = client.enviar(factura)

resultado.aceptado     # True
resultado.descripcion  # "La Factura numero F001-123, ha sido aceptada"
resultado.hash         # DigestValue (para la representación impresa)
resultado.qr           # contenido del código QR
resultado.cdr_xml      # guárdalo: es la prueba legal de aceptación
```

Los importes aceptan `Decimal`, `str` o `int`. Cada ítem indica **uno** de:

- `precio` — precio de venta unitario **con IGV** (lo que paga el cliente), o
- `valor` — valor unitario **sin IGV**.

## Casuísticas

### Factura al crédito (cuotas)

```python
from datetime import date
from sunat_see import Credito, Cuota

factura = Factura(
    serie="F001", numero=124, emisor=emisor, cliente=cliente,
    items=[Item("Servicio de consultoría", 1, valor="2050.00", unidad="ZZ")],
    forma_pago=Credito([
        Cuota(monto="1000.00", vencimiento=date(2026, 11, 15)),
        Cuota(monto="1419.00", vencimiento=date(2026, 12, 15)),
    ]),
)
```

El SDK valida que la suma de cuotas iguale el total y que los vencimientos sean
posteriores a la emisión (R.S. 193-2020). Al contado es el valor por defecto.

### Boleta de venta

```python
from sunat_see import Boleta

boleta = Boleta(
    serie="B001", numero=45, emisor=emisor,
    cliente=Cliente.con_dni("45678912", "JUAN PEREZ"),
    items=[Item("Menú del día", 1, precio="15.00")],
)

# Consumidor final sin documento (válido hasta S/ 700):
boleta = Boleta(
    serie="B002", numero=8, emisor=emisor,
    cliente=Cliente.publico_general(),
    items=[Item("Gaseosa", 2, precio="3.50")],
)
```

En **producción** las boletas se informan a SUNAT con un **resumen diario**
(asíncrono); en beta puedes enviarlas individualmente con `client.enviar(boleta)`.

```python
from sunat_see import ResumenDiario

resumen = ResumenDiario(emisor=emisor, boletas=[boleta1, boleta2])
envio = client.enviar_resumen(resumen)          # → ticket

estado = client.consultar_ticket(envio.ticket)  # repetir hasta que no esté en proceso
estado.en_proceso, estado.aceptado, estado.descripcion
```

El resumen también anula boletas ya informadas: `ResumenDiario(..., anular=[boleta])`.

### Nota de crédito

```python
from sunat_see import NotaCredito, MotivoNotaCredito

nc = NotaCredito(
    serie="FC01", numero=7, emisor=emisor, cliente=cliente,
    afecta=factura,                                   # o Referencia("01", "F001", 123)
    motivo=MotivoNotaCredito.DEVOLUCION_POR_ITEM,     # catálogo 09 (acepta "07")
    items=[Item("Mouse inalámbrico", 1, precio="59.00")],
)
resultado = client.enviar(nc)
```

La serie debe ser coherente con el documento afectado (empieza con `F` si afecta
una factura, `B` si afecta una boleta) — el SDK lo valida.

### Nota de débito

```python
from sunat_see import NotaDebito, MotivoNotaDebito

nd = NotaDebito(
    serie="FD01", numero=2, emisor=emisor, cliente=cliente,
    afecta=factura,
    motivo=MotivoNotaDebito.INTERESES_POR_MORA,       # catálogo 10
    items=[Item("Interés por mora", 1, valor="50.00", unidad="ZZ")],
)
```

### Ítems exonerados / inafectos / exportación

```python
from sunat_see import Afectacion

Item("Libro", 1, precio="50.00", afectacion=Afectacion.EXONERADO)
Item("Servicio en zona franca", 1, valor="200.00", afectacion=Afectacion.INAFECTO)
```

El SDK asigna el tributo correcto por línea (IGV 1000 / EXO 9997 / INA 9998 /
EXP 9995) y separa las bases en los totales.

## Ambientes

```python
# Beta: usuario MODDATOS y certificado autofirmado generado al vuelo.
client = SunatClient.beta(ruc="20123456789")

# Producción: usuario SOL secundario + certificado .pfx del emisor.
client = SunatClient.produccion(
    ruc="20123456789",
    usuario_sol="FACTURA1",
    clave_sol="...",
    cert_pfx=open("certificado.pfx", "rb").read(),
    cert_password="...",
)
```

| | Beta | Producción |
|---|---|---|
| Usuario | `<RUC>MODDATOS` / `MODDATOS` | `<RUC><usuario SOL secundario>` |
| Certificado | cualquiera (autofirmado OK) | `.pfx` del emisor, registrado en SUNAT |
| Valida | solo estructura del XML | estructura + consistencia + emisor |

## Sin enviar: solo generar XML firmado

```python
firmado = client.firmar(factura)
firmado.nombre   # "20123456789-01-F001-123"
firmado.xml      # UBL firmado (bytes)
firmado.hash     # DigestValue
firmado.qr       # contenido del QR

xml_sin_firmar = factura.xml()   # también disponible, sin cliente
```

## Qué guarda tu aplicación

El SDK es **sin estado**: tu aplicación asigna series y correlativos (de forma
transaccional, para no duplicar) y conserva `xml_firmado` y `cdr_xml` de cada
envío — es una obligación legal.

## Alcance y roadmap

Soportado: factura (01) contado/crédito, boleta (03), nota de crédito (07),
nota de débito (08), resumen diario de boletas (RC), IGV 18 %, afectaciones
onerosas (gravado/exonerado/inafecto/exportación), PEN/USD/EUR.

Aún no: operaciones gratuitas, detracciones, retenciones/percepciones,
anticipos, descuentos globales, guías de remisión, comunicación de baja (RA),
ISC/ICBPER.

## Desarrollo

```bash
uv venv && uv pip install -e ".[dev]"
pytest
```
