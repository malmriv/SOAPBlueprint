import json
import uuid

from lxml import etree

from .models import Field, ServiceConfig

NS_XSD = "http://www.w3.org/2001/XMLSchema"
NS_WSDL = "http://schemas.xmlsoap.org/wsdl/"
NS_SOAP = "http://schemas.xmlsoap.org/wsdl/soap/"
NS_WSOAP12 = "http://schemas.xmlsoap.org/wsdl/soap12/"


def _qn(ns: str, local: str) -> str:
    """Build a Clark-notation qualified name."""
    return f"{{{ns}}}{local}"


def _add_field_element(parent: etree._Element, field: Field) -> None:
    """Recursively add a Field as an xsd:element under *parent*."""
    attrs = {"name": field.name}
    if not field.is_complex:
        attrs["type"] = f"xsd:{field.type}"
    attrs["minOccurs"] = str(field.min_occurs)
    attrs["maxOccurs"] = str(field.max_occurs)

    elem = etree.SubElement(parent, _qn(NS_XSD, "element"), attrib=attrs)

    if field.is_complex:
        ct = etree.SubElement(elem, _qn(NS_XSD, "complexType"))
        seq = etree.SubElement(ct, _qn(NS_XSD, "sequence"))
        for child in field.children:
            _add_field_element(seq, child)


def _build_root_element(
    schema: etree._Element, element_name: str, fields: list[Field]
) -> None:
    """Build a top-level xsd:element (Z_Operacion_Request or _Response)."""
    root_el = etree.SubElement(
        schema, _qn(NS_XSD, "element"), attrib={"name": element_name}
    )
    ct = etree.SubElement(root_el, _qn(NS_XSD, "complexType"))
    seq = etree.SubElement(ct, _qn(NS_XSD, "sequence"))
    for field in fields:
        _add_field_element(seq, field)


def _build_message(
    root: etree._Element, msg_name: str, element_name: str, tns: str
) -> None:
    msg = etree.SubElement(root, _qn(NS_WSDL, "message"), attrib={"name": msg_name})
    etree.SubElement(
        msg, _qn(NS_WSDL, "part"),
        attrib={"name": "parameters", "element": f"tns:{element_name}"},
    )


def generate_wsdl(
    config: ServiceConfig,
    request_fields: list[Field],
    response_fields: list[Field],
) -> str:
    """Generate a complete WSDL document compatible with SAP Integration Suite."""
    tns = config.target_namespace
    nsmap = {
        "xsd": NS_XSD,
        "wsdl": NS_WSDL,
        "soap": NS_SOAP,
        "wsoap12": NS_WSOAP12,
        "tns": tns,
    }

    # -- wsdl:definitions --
    root = etree.Element(_qn(NS_WSDL, "definitions"), nsmap=nsmap)
    root.set("targetNamespace", tns)

    # -- wsdl:types / xsd:schema --
    types = etree.SubElement(root, _qn(NS_WSDL, "types"))
    schema = etree.SubElement(types, _qn(NS_XSD, "schema"))
    schema.set("targetNamespace", tns)

    req_el = config.request_element
    resp_el = config.response_element

    _build_root_element(schema, req_el, request_fields)
    _build_root_element(schema, resp_el, response_fields)

    # -- wsdl:message --
    req_msg = f"Message_{req_el}"
    resp_msg = f"Message_{resp_el}"
    _build_message(root, req_msg, req_el, tns)
    _build_message(root, resp_msg, resp_el, tns)

    # -- wsdl:portType --
    op_name = f"Operation_{req_el}"
    port_type = etree.SubElement(
        root, _qn(NS_WSDL, "portType"), attrib={"name": "Port_RequestResponse"}
    )
    operation = etree.SubElement(
        port_type, _qn(NS_WSDL, "operation"), attrib={"name": op_name}
    )
    etree.SubElement(
        operation, _qn(NS_WSDL, "input"),
        attrib={"message": f"tns:{req_msg}"},
    )
    etree.SubElement(
        operation, _qn(NS_WSDL, "output"),
        attrib={"message": f"tns:{resp_msg}"},
    )

    # -- wsdl:binding (SOAP 1.2) --
    binding = etree.SubElement(
        root, _qn(NS_WSDL, "binding"),
        attrib={"name": "SOAPBinding_Webservice", "type": "tns:Port_RequestResponse"},
    )
    etree.SubElement(
        binding, _qn(NS_WSOAP12, "binding"),
        attrib={"style": "document", "transport": "http://schemas.xmlsoap.org/soap/http"},
    )
    bind_op = etree.SubElement(
        binding, _qn(NS_WSDL, "operation"), attrib={"name": op_name}
    )
    bind_input = etree.SubElement(bind_op, _qn(NS_WSDL, "input"))
    etree.SubElement(bind_input, _qn(NS_WSOAP12, "body"), attrib={"use": "literal"})
    bind_output = etree.SubElement(bind_op, _qn(NS_WSDL, "output"))
    etree.SubElement(bind_output, _qn(NS_WSOAP12, "body"), attrib={"use": "literal"})

    # -- wsdl:service --
    service = etree.SubElement(
        root, _qn(NS_WSDL, "service"),
        attrib={"name": f"Webservice_{config.service_name}"},
    )
    port = etree.SubElement(
        service, _qn(NS_WSDL, "port"),
        attrib={
            "name": "Port_RequestResponse",
            "binding": "tns:SOAPBinding_Webservice",
        },
    )
    etree.SubElement(
        port, _qn(NS_SOAP, "address"), attrib={"location": tns}
    )

    return etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    ).decode("utf-8")


NS_SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"

_SAMPLE_VALUES = {
    "string": "Example",
    "int": "0",
    "integer": "0",
    "long": "0",
    "short": "0",
    "decimal": "0.00",
    "float": "0.00",
    "double": "0.00",
    "boolean": "true",
    "date": "2026-01-01",
    "dateTime": "2026-01-01T00:00:00",
    "time": "00:00:00",
    "base64Binary": "SGVsbG8=",
    "hexBinary": "48656C6C6F",
}


def _add_sample_field(parent: etree._Element, field: Field) -> None:
    """Recursively add a sample field element (no namespace on children)."""
    elem = etree.SubElement(parent, field.name)
    if field.is_complex:
        for child in field.children:
            _add_sample_field(elem, child)
    else:
        elem.text = _SAMPLE_VALUES.get(field.type, "?")


def generate_sample_message(
    config: ServiceConfig,
    fields: list[Field],
    element_name: str,
) -> str:
    """Generate a sample SOAP message for the given fields."""
    tns = config.target_namespace
    nsmap = {
        "soap": NS_SOAP_ENV,
        "ns": tns,
    }

    envelope = etree.Element(_qn(NS_SOAP_ENV, "Envelope"), nsmap=nsmap)
    etree.SubElement(envelope, _qn(NS_SOAP_ENV, "Header"))
    body = etree.SubElement(envelope, _qn(NS_SOAP_ENV, "Body"))

    operation = etree.SubElement(body, _qn(tns, element_name))
    for field in fields:
        _add_sample_field(operation, field)

    return etree.tostring(
        envelope, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    ).decode("utf-8")


def generate_postman_collection(
    config: ServiceConfig,
    request_fields: list[Field],
) -> str:
    """Generate a Postman collection JSON with the sample SOAP request."""
    sample_xml = generate_sample_message(
        config, request_fields, config.request_element
    )
    collection = {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": config.service_name,
            "description": "This collection was automatically generated by SOAP Blueprint.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Request",
                "request": {
                    "method": "POST",
                    "header": [
                        {
                            "key": "Content-Type",
                            "value": "text/xml",
                            "type": "text",
                        }
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": sample_xml,
                        "options": {
                            "raw": {
                                "language": "xml",
                            }
                        },
                    },
                    "url": {
                        "raw": "{{SOAPServiceURL}}",
                        "host": ["{{SOAPServiceURL}}"],
                    },
                },
                "response": [],
            }
        ],
    }
    return json.dumps(collection, indent=2, ensure_ascii=False)


def generate_xsd(
    config: ServiceConfig,
    request_fields: list[Field],
    response_fields: list[Field],
) -> str:
    """Extract just the XSD schema with its own namespace declaration."""
    tns = config.target_namespace
    nsmap = {"xsd": NS_XSD}

    schema = etree.Element(_qn(NS_XSD, "schema"), nsmap=nsmap)
    schema.set("targetNamespace", tns)

    _build_root_element(schema, config.request_element, request_fields)
    _build_root_element(schema, config.response_element, response_fields)

    return etree.tostring(
        schema, pretty_print=True, xml_declaration=False, encoding="unicode"
    )
