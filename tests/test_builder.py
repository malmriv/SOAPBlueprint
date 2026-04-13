import pytest
from lxml import etree

from core.models import Field, ServiceConfig
from core.builder import generate_wsdl
from core.validators import validate_field, validate_field_name, ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NS = {
    "xsd": "http://www.w3.org/2001/XMLSchema",
    "wsdl": "http://schemas.xmlsoap.org/wsdl/",
    "soap": "http://schemas.xmlsoap.org/wsdl/soap/",
    "wsoap12": "http://schemas.xmlsoap.org/wsdl/soap12/",
}

DEFAULT_CONFIG = ServiceConfig(service_name="TestService")


def _parse(xml_str: str) -> etree._Element:
    return etree.fromstring(xml_str.encode("utf-8"))


def _request_fields(root: etree._Element, name: str = "ZRequest") -> etree._Element:
    """Return the xsd:sequence inside the request element."""
    return root.xpath(
        f"//xsd:element[@name='{name}']"
        "/xsd:complexType/xsd:sequence",
        namespaces=NS,
    )[0]


def _response_fields(root: etree._Element, name: str = "ZResponse") -> etree._Element:
    return root.xpath(
        f"//xsd:element[@name='{name}']"
        "/xsd:complexType/xsd:sequence",
        namespaces=NS,
    )[0]


# ---------------------------------------------------------------------------
# WSDL skeleton tests
# ---------------------------------------------------------------------------

class TestWsdlSkeleton:
    """Verify the fixed parts of the WSDL are emitted correctly."""

    def test_valid_xml(self):
        xml = generate_wsdl(DEFAULT_CONFIG, [], [])
        root = _parse(xml)
        assert root.tag == f"{{{NS['wsdl']}}}definitions"

    def test_target_namespace(self):
        xml = generate_wsdl(DEFAULT_CONFIG, [], [])
        root = _parse(xml)
        assert root.get("targetNamespace") == "http://example.com/TestService"

    def test_messages_exist(self):
        xml = generate_wsdl(DEFAULT_CONFIG, [], [])
        root = _parse(xml)
        msgs = root.xpath("//wsdl:message/@name", namespaces=NS)
        assert "Message_ZRequest" in msgs
        assert "Message_ZResponse" in msgs

    def test_port_type_and_binding(self):
        xml = generate_wsdl(DEFAULT_CONFIG, [], [])
        root = _parse(xml)
        assert root.xpath("//wsdl:portType[@name='Port_RequestResponse']", namespaces=NS)
        assert root.xpath("//wsdl:binding[@name='SOAPBinding_Webservice']", namespaces=NS)

    def test_service_name(self):
        cfg = ServiceConfig(service_name="MyWebService")
        xml = generate_wsdl(cfg, [], [])
        root = _parse(xml)
        services = root.xpath("//wsdl:service/@name", namespaces=NS)
        assert "Webservice_MyWebService" in services

    def test_custom_element_names(self):
        cfg = ServiceConfig(
            service_name="Svc",
            request_element="Z_MyRequest",
            response_element="Z_MyResponse",
        )
        xml = generate_wsdl(cfg, [Field(name="A", type="string")], [])
        root = _parse(xml)
        seq = _request_fields(root, name="Z_MyRequest")
        assert seq.xpath("xsd:element[@name='A']", namespaces=NS)
        msgs = root.xpath("//wsdl:message/@name", namespaces=NS)
        assert "Message_Z_MyRequest" in msgs
        assert "Message_Z_MyResponse" in msgs

    def test_soap12_binding(self):
        xml = generate_wsdl(DEFAULT_CONFIG, [], [])
        root = _parse(xml)
        soap_bindings = root.xpath("//wsoap12:binding", namespaces=NS)
        assert len(soap_bindings) == 1
        assert soap_bindings[0].get("style") == "document"


# ---------------------------------------------------------------------------
# Flat (leaf) fields
# ---------------------------------------------------------------------------

class TestFlatFields:
    def test_single_string_field(self):
        fields = [Field(name="Name", type="string")]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        seq = _request_fields(root)
        elems = seq.xpath("xsd:element", namespaces=NS)
        assert len(elems) == 1
        assert elems[0].get("name") == "Name"
        assert elems[0].get("type") == "xsd:string"
        assert elems[0].get("minOccurs") == "0"
        assert elems[0].get("maxOccurs") == "1"

    def test_multiple_flat_fields(self):
        fields = [
            Field(name="Name", type="string"),
            Field(name="Age", type="int", min_occurs=1),
            Field(name="Active", type="boolean"),
        ]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        seq = _request_fields(root)
        names = [e.get("name") for e in seq.xpath("xsd:element", namespaces=NS)]
        assert names == ["Name", "Age", "Active"]

    def test_min_occurs_preserved(self):
        fields = [Field(name="Required", type="string", min_occurs=1)]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        seq = _request_fields(root)
        elem = seq.xpath("xsd:element[@name='Required']", namespaces=NS)[0]
        assert elem.get("minOccurs") == "1"


# ---------------------------------------------------------------------------
# One level of nesting (complex field with children)
# ---------------------------------------------------------------------------

class TestOneLevel:
    def test_complex_field_structure(self):
        fields = [
            Field(name="User", children=[
                Field(name="FirstName", type="string"),
                Field(name="LastName", type="string"),
            ]),
        ]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        seq = _request_fields(root)
        user = seq.xpath("xsd:element[@name='User']", namespaces=NS)
        assert len(user) == 1
        inner_seq = user[0].xpath(
            "xsd:complexType/xsd:sequence/xsd:element", namespaces=NS
        )
        assert len(inner_seq) == 2
        assert inner_seq[0].get("name") == "FirstName"
        assert inner_seq[1].get("name") == "LastName"

    def test_complex_field_has_no_type_attribute(self):
        fields = [
            Field(name="Data", children=[
                Field(name="X", type="int"),
            ]),
        ]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        seq = _request_fields(root)
        data = seq.xpath("xsd:element[@name='Data']", namespaces=NS)[0]
        assert data.get("type") is None


# ---------------------------------------------------------------------------
# Deep nesting (3+ levels)
# ---------------------------------------------------------------------------

class TestDeepNesting:
    def test_three_levels(self):
        fields = [
            Field(name="Level1", children=[
                Field(name="Level2", children=[
                    Field(name="Level3", type="string"),
                ]),
            ]),
        ]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        leaf = root.xpath(
            "//xsd:element[@name='ZRequest']"
            "/xsd:complexType/xsd:sequence"
            "/xsd:element[@name='Level1']"
            "/xsd:complexType/xsd:sequence"
            "/xsd:element[@name='Level2']"
            "/xsd:complexType/xsd:sequence"
            "/xsd:element[@name='Level3']",
            namespaces=NS,
        )
        assert len(leaf) == 1
        assert leaf[0].get("type") == "xsd:string"

    def test_four_levels(self):
        fields = [
            Field(name="A", children=[
                Field(name="B", children=[
                    Field(name="C", children=[
                        Field(name="D", type="decimal"),
                    ]),
                ]),
            ]),
        ]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        d_elems = root.xpath("//xsd:element[@name='D']", namespaces=NS)
        assert len(d_elems) == 1
        assert d_elems[0].get("type") == "xsd:decimal"


# ---------------------------------------------------------------------------
# Arrays (maxOccurs="unbounded")
# ---------------------------------------------------------------------------

class TestArrays:
    def test_unbounded_leaf(self):
        fields = [Field(name="Item", type="string", max_occurs="unbounded")]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        seq = _request_fields(root)
        elem = seq.xpath("xsd:element[@name='Item']", namespaces=NS)[0]
        assert elem.get("maxOccurs") == "unbounded"

    def test_unbounded_complex(self):
        fields = [
            Field(name="Lines", max_occurs="unbounded", children=[
                Field(name="Product", type="string"),
                Field(name="Quantity", type="int"),
            ]),
        ]
        xml = generate_wsdl(DEFAULT_CONFIG, fields, [])
        root = _parse(xml)
        seq = _request_fields(root)
        lines = seq.xpath("xsd:element[@name='Lines']", namespaces=NS)[0]
        assert lines.get("maxOccurs") == "unbounded"
        children = lines.xpath(
            "xsd:complexType/xsd:sequence/xsd:element", namespaces=NS
        )
        assert len(children) == 2


# ---------------------------------------------------------------------------
# Response fields
# ---------------------------------------------------------------------------

class TestResponseFields:
    def test_response_fields_independent(self):
        req = [Field(name="Input", type="string")]
        resp = [Field(name="Code", type="string"), Field(name="Message", type="string")]
        xml = generate_wsdl(DEFAULT_CONFIG, req, resp)
        root = _parse(xml)

        req_names = [
            e.get("name")
            for e in _request_fields(root).xpath("xsd:element", namespaces=NS)
        ]
        resp_names = [
            e.get("name")
            for e in _response_fields(root).xpath("xsd:element", namespaces=NS)
        ]
        assert req_names == ["Input"]
        assert resp_names == ["Code", "Message"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_field_name("")

    def test_name_with_spaces_rejected(self):
        with pytest.raises(ValidationError, match="Invalid XML name"):
            validate_field_name("My Field")

    def test_name_starting_with_digit_rejected(self):
        with pytest.raises(ValidationError, match="Invalid XML name"):
            validate_field_name("1Field")

    def test_valid_names_accepted(self):
        for name in ["Field", "_field", "My_Field", "field.sub", "A1"]:
            validate_field_name(name)  # should not raise

    def test_unknown_type_rejected(self):
        f = Field(name="X", type="varchar")
        with pytest.raises(ValidationError, match="unknown type"):
            validate_field(f)

    def test_negative_min_occurs(self):
        f = Field(name="X", type="string", min_occurs=-1)
        with pytest.raises(ValidationError, match="min_occurs"):
            validate_field(f)

    def test_zero_max_occurs(self):
        f = Field(name="X", type="string", max_occurs=0)
        with pytest.raises(ValidationError, match="max_occurs"):
            validate_field(f)

    def test_invalid_max_occurs_string(self):
        f = Field(name="X", type="string", max_occurs="many")
        with pytest.raises(ValidationError, match="max_occurs"):
            validate_field(f)

    def test_recursive_validation(self):
        f = Field(name="Parent", children=[
            Field(name="OK", type="string"),
            Field(name="Bad Child", type="string"),  # space in name
        ])
        with pytest.raises(ValidationError, match="Invalid XML name"):
            validate_field(f)
