import pytest

from core.models import Field, ServiceConfig
from core.builder import generate_wsdl
from core.parser import parse_wsdl, ParseError


def _round_trip(config: ServiceConfig, req, resp):
    xml = generate_wsdl(config, req, resp)
    return parse_wsdl(xml.encode("utf-8"))


class TestRoundTrip:
    def test_minimal(self):
        cfg = ServiceConfig(service_name="MyService")
        parsed_cfg, req, resp = _round_trip(cfg, [], [])
        assert parsed_cfg.service_name == "MyService"
        assert parsed_cfg.namespace_base == "http://example.com"
        assert parsed_cfg.request_element == "ZRequest"
        assert parsed_cfg.response_element == "ZResponse"
        assert req == []
        assert resp == []

    def test_custom_element_names(self):
        cfg = ServiceConfig(
            service_name="Svc",
            namespace_base="http://my.org",
            request_element="Z_In",
            response_element="Z_Out",
        )
        parsed_cfg, _, _ = _round_trip(cfg, [], [])
        assert parsed_cfg.service_name == "Svc"
        assert parsed_cfg.namespace_base == "http://my.org"
        assert parsed_cfg.request_element == "Z_In"
        assert parsed_cfg.response_element == "Z_Out"

    def test_flat_fields(self):
        cfg = ServiceConfig(service_name="S")
        req = [
            Field(name="Name", type="string"),
            Field(name="Age", type="int", min_occurs=1),
        ]
        _, parsed_req, _ = _round_trip(cfg, req, [])
        assert len(parsed_req) == 2
        assert parsed_req[0].name == "Name"
        assert parsed_req[0].type == "string"
        assert parsed_req[1].name == "Age"
        assert parsed_req[1].type == "int"
        assert parsed_req[1].min_occurs == 1

    def test_nested_fields(self):
        cfg = ServiceConfig(service_name="S")
        req = [
            Field(name="User", children=[
                Field(name="FirstName", type="string"),
                Field(name="LastName", type="string"),
            ]),
        ]
        _, parsed_req, _ = _round_trip(cfg, req, [])
        assert len(parsed_req) == 1
        assert parsed_req[0].name == "User"
        assert parsed_req[0].is_complex
        assert len(parsed_req[0].children) == 2
        assert parsed_req[0].children[0].name == "FirstName"
        assert parsed_req[0].children[1].name == "LastName"

    def test_deep_nesting(self):
        cfg = ServiceConfig(service_name="S")
        req = [
            Field(name="A", children=[
                Field(name="B", children=[
                    Field(name="C", children=[
                        Field(name="D", type="decimal"),
                    ]),
                ]),
            ]),
        ]
        _, parsed_req, _ = _round_trip(cfg, req, [])
        d = parsed_req[0].children[0].children[0].children[0]
        assert d.name == "D"
        assert d.type == "decimal"

    def test_unbounded(self):
        cfg = ServiceConfig(service_name="S")
        req = [Field(name="Item", type="string", max_occurs="unbounded")]
        _, parsed_req, _ = _round_trip(cfg, req, [])
        assert parsed_req[0].max_occurs == "unbounded"

    def test_response_independent(self):
        cfg = ServiceConfig(service_name="S")
        req = [Field(name="In", type="string")]
        resp = [Field(name="Out", type="int")]
        _, parsed_req, parsed_resp = _round_trip(cfg, req, resp)
        assert parsed_req[0].name == "In"
        assert parsed_resp[0].name == "Out"
        assert parsed_resp[0].type == "int"


class TestErrors:
    def test_invalid_xml(self):
        with pytest.raises(ParseError, match="Invalid XML"):
            parse_wsdl(b"<not-valid")

    def test_missing_target_namespace(self):
        xml = (
            b'<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"/>'
        )
        with pytest.raises(ParseError, match="targetNamespace"):
            parse_wsdl(xml)

    def test_missing_service(self):
        xml = (
            b'<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" '
            b'targetNamespace="http://x/y"/>'
        )
        with pytest.raises(ParseError, match="wsdl:service"):
            parse_wsdl(xml)
