from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Field:
    name: str
    type: str = "string"
    min_occurs: int = 0
    max_occurs: int | str = 1  # int or "unbounded"
    children: list[Field] = field(default_factory=list)

    @property
    def is_complex(self) -> bool:
        return len(self.children) > 0


@dataclass
class ServiceConfig:
    service_name: str  # e.g. "MyWebService"
    namespace_base: str = "http://example.com"
    request_element: str = "ZRequest"
    response_element: str = "ZResponse"

    @property
    def target_namespace(self) -> str:
        return f"{self.namespace_base.rstrip('/')}/{self.service_name}"
