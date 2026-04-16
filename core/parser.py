from lxml import etree

from .models import Field, ServiceConfig

NS_XSD = "http://www.w3.org/2001/XMLSchema"
NS_WSDL = "http://schemas.xmlsoap.org/wsdl/"


class ParseError(Exception):
    pass


def _parse_element(elem: etree._Element) -> Field:
    """Parse an xsd:element into a Field, recursing into children if complex."""
    name = elem.get("name")
    if not name:
        raise ParseError("Found an xsd:element without a 'name' attribute.")

    min_occurs = int(elem.get("minOccurs", "1"))
    max_occurs_raw = elem.get("maxOccurs", "1")
    max_occurs = (
        "unbounded" if max_occurs_raw == "unbounded" else int(max_occurs_raw)
    )

    complex_type = elem.find(f"{{{NS_XSD}}}complexType")
    if complex_type is not None:
        sequence = complex_type.find(f"{{{NS_XSD}}}sequence")
        children = []
        if sequence is not None:
            for child_elem in sequence.findall(f"{{{NS_XSD}}}element"):
                children.append(_parse_element(child_elem))
        return Field(
            name=name,
            type="string",  # ignored for complex fields
            min_occurs=min_occurs,
            max_occurs=max_occurs,
            children=children,
        )

    type_attr = elem.get("type", "xsd:string")
    type_name = type_attr.split(":")[-1]
    return Field(
        name=name,
        type=type_name,
        min_occurs=min_occurs,
        max_occurs=max_occurs,
    )


def parse_wsdl(xml_bytes: bytes) -> tuple[ServiceConfig, list[Field], list[Field]]:
    """Parse a WSDL previously produced by SOAP Blueprint.

    Returns (config, request_fields, response_fields). Raises ParseError if the
    WSDL does not have the expected structure.
    """
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as e:
        raise ParseError(f"Invalid XML: {e}")

    tns = root.get("targetNamespace")
    if not tns:
        raise ParseError("Missing targetNamespace on wsdl:definitions.")

    service = root.find(f"{{{NS_WSDL}}}service")
    if service is None:
        raise ParseError("Missing wsdl:service element.")

    service_name_attr = service.get("name", "")
    if service_name_attr.startswith("Webservice_"):
        service_name = service_name_attr[len("Webservice_"):]
    else:
        service_name = service_name_attr

    if tns.endswith("/" + service_name):
        namespace_base = tns[: -(len(service_name) + 1)]
    else:
        namespace_base = tns

    schema = root.find(f"{{{NS_WSDL}}}types/{{{NS_XSD}}}schema")
    if schema is None:
        raise ParseError("Missing xsd:schema inside wsdl:types.")

    top_elements = schema.findall(f"{{{NS_XSD}}}element")
    if len(top_elements) < 2:
        raise ParseError(
            f"Expected two top-level xsd:element nodes (request and response), "
            f"found {len(top_elements)}."
        )

    request_elem, response_elem = top_elements[0], top_elements[1]
    request_element_name = request_elem.get("name")
    response_element_name = response_elem.get("name")

    def extract_fields(top_elem: etree._Element) -> list[Field]:
        ct = top_elem.find(f"{{{NS_XSD}}}complexType")
        if ct is None:
            return []
        seq = ct.find(f"{{{NS_XSD}}}sequence")
        if seq is None:
            return []
        return [_parse_element(e) for e in seq.findall(f"{{{NS_XSD}}}element")]

    request_fields = extract_fields(request_elem)
    response_fields = extract_fields(response_elem)

    config = ServiceConfig(
        service_name=service_name,
        namespace_base=namespace_base,
        request_element=request_element_name,
        response_element=response_element_name,
    )

    return config, request_fields, response_fields
