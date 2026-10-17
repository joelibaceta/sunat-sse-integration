from lxml import etree

from sunat_see.signer import generate_self_signed_cert, sign_xml
from sunat_see.ubl import EXT, build_xml

DS = "http://www.w3.org/2000/09/xmldsig#"


def test_firma_queda_dentro_de_extension_content(factura):
    cert, key = generate_self_signed_cert()
    signed, digest = sign_xml(build_xml(factura), cert, key)

    root = etree.fromstring(signed)
    firma = root.find(
        f"{{{EXT}}}UBLExtensions/{{{EXT}}}UBLExtension/"
        f"{{{EXT}}}ExtensionContent/{{{DS}}}Signature"
    )
    assert firma is not None
    assert firma.get("Id") == "SignatureSP"
    assert digest  # DigestValue para el QR / representación impresa
    # No debe quedar otra firma suelta en el root.
    assert len(root.findall(f"{{{DS}}}Signature")) == 0


def test_firma_es_verificable(factura):
    from signxml import XMLVerifier

    cert, key = generate_self_signed_cert()
    signed, _ = sign_xml(build_xml(factura), cert, key)
    root = etree.fromstring(signed)
    XMLVerifier().verify(root, x509_cert=cert.decode())
