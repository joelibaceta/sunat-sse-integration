"""Cliente de alto nivel: construye, firma, envía y lee la respuesta de SUNAT.

Uso típico::

    client = SunatClient.beta(ruc="20123456789")
    resultado = client.enviar(factura)       # → Resultado (CDR síncrono)

    envio = client.enviar_resumen(resumen)   # boletas → ticket asíncrono
    estado = client.consultar_ticket(envio.ticket)
"""
from __future__ import annotations

from dataclasses import dataclass

from .baja import ComunicacionBaja, build_baja_xml
from .cdr import parse_cdr_zip
from .documents import Boleta, Factura, NotaCredito, NotaDebito, _Comprobante
from .exceptions import SoapFault
from .signer import generate_self_signed_cert, load_pfx, sign_xml
from .soap import SoapClient
from .summary import ResumenDiario, build_resumen_xml
from .ubl import build_xml

ENDPOINT_BETA = "https://e-beta.sunat.gob.pe/ol-ti-itcpfegem-beta/billService"
ENDPOINT_PRODUCCION = "https://e-factura.sunat.gob.pe/ol-ti-itcpfegem/billService"

Comprobante = Factura | Boleta | NotaCredito | NotaDebito


@dataclass(frozen=True)
class Firmado:
    """Comprobante firmado, listo para enviar o para generar la representación impresa."""

    nombre: str        # <RUC>-<tipo>-<serie>-<numero> (nombre de archivo sin extensión)
    xml: bytes         # UBL firmado
    hash: str          # DigestValue de la firma (va impreso y en el QR)
    qr: str            # contenido del código QR (R.S. 193-2020)


@dataclass(frozen=True)
class Resultado:
    """Respuesta de SUNAT a un envío síncrono (``sendBill``)."""

    aceptado: bool
    codigo: str        # "0" = aceptado; 2000–3999 rechazado; 4000+ observado
    descripcion: str
    nombre: str
    hash: str
    qr: str
    xml_firmado: bytes  # conservar (obligación legal)
    cdr_xml: bytes      # conservar (prueba de aceptación)
    cdr_zip: bytes


@dataclass(frozen=True)
class ResumenEnviado:
    ticket: str
    nombre: str
    xml_firmado: bytes


@dataclass(frozen=True)
class ResultadoTicket:
    """Estado de un resumen diario (``getStatus``)."""

    en_proceso: bool
    aceptado: bool
    codigo: str | None
    descripcion: str | None
    cdr_xml: bytes | None
    cdr_zip: bytes | None


class SunatClient:
    """Cliente del SEE (billService). Crea instancias con ``beta()`` o ``produccion()``."""

    def __init__(self, *, ruc: str, usuario_sol: str, clave_sol: str,
                 cert_pem: bytes, key_pem: bytes, endpoint: str, timeout: int = 60):
        self.ruc = ruc
        self._soap = SoapClient(
            endpoint=endpoint,
            username=f"{ruc}{usuario_sol}",
            password=clave_sol,
            timeout=timeout,
        )
        self._cert_pem = cert_pem
        self._key_pem = key_pem

    @classmethod
    def beta(cls, ruc: str, *, timeout: int = 60) -> "SunatClient":
        """Ambiente de pruebas: usuario ``MODDATOS`` y certificado autofirmado generado al vuelo.

        SUNAT beta solo valida la estructura del XML, no el certificado ni el emisor.
        No usar beta para pruebas de estrés (restricción de SUNAT).
        """
        cert_pem, key_pem = generate_self_signed_cert()
        return cls(ruc=ruc, usuario_sol="MODDATOS", clave_sol="MODDATOS",
                   cert_pem=cert_pem, key_pem=key_pem, endpoint=ENDPOINT_BETA, timeout=timeout)

    @classmethod
    def produccion(cls, *, ruc: str, usuario_sol: str, clave_sol: str,
                   cert_pfx: bytes, cert_password: str, timeout: int = 60) -> "SunatClient":
        """Ambiente real: usuario SOL secundario y certificado ``.pfx`` del emisor."""
        cert_pem, key_pem = load_pfx(cert_pfx, cert_password)
        return cls(ruc=ruc, usuario_sol=usuario_sol, clave_sol=clave_sol,
                   cert_pem=cert_pem, key_pem=key_pem, endpoint=ENDPOINT_PRODUCCION, timeout=timeout)

    # --- Comprobantes individuales -------------------------------------------

    def firmar(self, doc: Comprobante) -> Firmado:
        """Construye el XML UBL, lo firma y devuelve el paquete listo para enviar."""
        xml = build_xml(doc)
        signed, digest = sign_xml(xml, self._cert_pem, self._key_pem)
        nombre = f"{doc.emisor.ruc}-{doc.tipo}-{doc.serie}-{doc.numero}"
        return Firmado(nombre=nombre, xml=signed, hash=digest, qr=_qr(doc, digest))

    def enviar(self, doc: Comprobante) -> Resultado:
        """Firma y envía por ``sendBill``; devuelve el CDR parseado.

        Nota: en producción las boletas no van por ``sendBill`` — se informan con
        ``enviar_resumen()``. En beta sí se aceptan individualmente, útil para probar.
        """
        firmado = self.firmar(doc)
        cdr_zip = self._soap.send_bill(firmado.nombre, firmado.xml)
        cdr = parse_cdr_zip(cdr_zip)
        return Resultado(
            aceptado=cdr.aceptado,
            codigo=cdr.codigo,
            descripcion=cdr.descripcion,
            nombre=firmado.nombre,
            hash=firmado.hash,
            qr=firmado.qr,
            xml_firmado=firmado.xml,
            cdr_xml=cdr.xml,
            cdr_zip=cdr_zip,
        )

    # --- Resumen diario de boletas --------------------------------------------

    def enviar_resumen(self, resumen: ResumenDiario) -> ResumenEnviado:
        """Firma y envía un resumen diario (``sendSummary``); devuelve el ticket."""
        xml = build_resumen_xml(resumen)
        signed, _digest = sign_xml(xml, self._cert_pem, self._key_pem)
        nombre = f"{resumen.emisor.ruc}-{resumen.full_id}"
        ticket = self._soap.send_summary(nombre, signed)
        return ResumenEnviado(ticket=ticket, nombre=nombre, xml_firmado=signed)

    def enviar_baja(self, baja: ComunicacionBaja) -> ResumenEnviado:
        """Firma y envía una Comunicación de Baja (``sendSummary``); devuelve el ticket.

        El CDR de la baja se recupera después con ``consultar_ticket()``.
        """
        xml = build_baja_xml(baja)
        signed, _digest = sign_xml(xml, self._cert_pem, self._key_pem)
        nombre = f"{baja.emisor.ruc}-{baja.full_id}"
        ticket = self._soap.send_summary(nombre, signed)
        return ResumenEnviado(ticket=ticket, nombre=nombre, xml_firmado=signed)

    def consultar_ticket(self, ticket: str) -> ResultadoTicket:
        """Consulta el estado de un resumen o baja (``getStatus``)."""
        try:
            status, content = self._soap.get_status(ticket)
        except SoapFault as exc:
            # El beta responde a veces un error interno (Server.200) al consultar
            # tickets de baja mientras los procesa; se trata como "en proceso".
            if "Server.200" in exc.codigo:
                return ResultadoTicket(en_proceso=True, aceptado=False, codigo=None,
                                       descripcion=None, cdr_xml=None, cdr_zip=None)
            raise
        if status == "98":
            return ResultadoTicket(en_proceso=True, aceptado=False, codigo=None,
                                   descripcion=None, cdr_xml=None, cdr_zip=None)
        if content:
            cdr = parse_cdr_zip(content)
            return ResultadoTicket(
                en_proceso=False,
                aceptado=(status == "0" and cdr.aceptado),
                codigo=cdr.codigo,
                descripcion=cdr.descripcion,
                cdr_xml=cdr.xml,
                cdr_zip=content,
            )
        return ResultadoTicket(en_proceso=False, aceptado=(status == "0"), codigo=status,
                               descripcion=None, cdr_xml=None, cdr_zip=None)


def _qr(doc: Comprobante, digest: str) -> str:
    """Contenido del código QR de la representación impresa (R.S. 193-2020)."""
    _, tot = doc.calcular()
    return "|".join([
        doc.emisor.ruc,
        doc.tipo,
        doc.serie,
        str(doc.numero),
        str(tot.igv),
        str(tot.total),
        doc.fecha_emision.isoformat(),
        doc.cliente.tipo_doc,
        doc.cliente.numero_doc,
        digest,
    ])
