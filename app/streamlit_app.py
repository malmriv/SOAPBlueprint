import base64
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "graphics", "header-image.png")

from core.models import Field, ServiceConfig
from core.builder import (
    generate_wsdl,
    generate_xsd,
    generate_sample_message,
    generate_postman_collection,
)
from core.validators import (
    validate_field,
    validate_service_name,
    ValidationError,
    ALLOWED_TYPES,
)


# ---------------------------------------------------------------------------
# Node helpers (UI-side tree state, not business logic)
# ---------------------------------------------------------------------------

def _new_node(name="NewField"):
    return {
        "uid": str(uuid.uuid4()),
        "name": name,
        "type": "string",
        "min_occurs": 0,
        "max_occurs": 1,
        "children": [],
    }


def _find_node(tree, uid):
    for node in tree:
        if node["uid"] == uid:
            return node
        found = _find_node(node["children"], uid)
        if found:
            return found
    return None


def _find_parent_list(tree, uid):
    """Return (list_containing_node, index) or None."""
    for i, node in enumerate(tree):
        if node["uid"] == uid:
            return tree, i
        result = _find_parent_list(node["children"], uid)
        if result:
            return result
    return None


def _delete_node(tree, uid):
    result = _find_parent_list(tree, uid)
    if result:
        lst, idx = result
        lst.pop(idx)


def _move_node(tree, uid, delta):
    result = _find_parent_list(tree, uid)
    if result:
        lst, idx = result
        new_idx = idx + delta
        if 0 <= new_idx < len(lst):
            lst[idx], lst[new_idx] = lst[new_idx], lst[idx]


def _nodes_to_fields(nodes):
    return [
        Field(
            name=n["name"],
            type=n["type"],
            min_occurs=n["min_occurs"],
            max_occurs=n["max_occurs"],
            children=_nodes_to_fields(n["children"]),
        )
        for n in nodes
    ]


def _flatten(nodes, depth=0):
    """Yield (node, depth) in display order (pre-order traversal)."""
    for node in nodes:
        yield node, depth
        yield from _flatten(node["children"], depth + 1)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_state():
    defaults = {
        "request_tree": [],
        "response_tree": [],
        "editing_uid": None,
        "editing_tree": None,
        "generated_wsdl": None,
        "generated_xsd": None,
        "sample_request": None,
        "sample_response": None,
        "postman_collection": None,
        "show_sample": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _reset_edit_keys(tree_key, uid, node):
    """Sync widget keys to the node's current values before opening editor."""
    st.session_state[f"name_{tree_key}_{uid}"] = node["name"]
    st.session_state[f"min_{tree_key}_{uid}"] = node["min_occurs"]
    st.session_state[f"unb_{tree_key}_{uid}"] = node["max_occurs"] == "unbounded"
    if isinstance(node["max_occurs"], int):
        st.session_state[f"max_{tree_key}_{uid}"] = node["max_occurs"]
    current_type = node["type"] if node["type"] in ALLOWED_TYPES else "string"
    st.session_state[f"type_{tree_key}_{uid}"] = current_type


# ---------------------------------------------------------------------------
# Tree rendering
# ---------------------------------------------------------------------------

_TYPE_OPTIONS = sorted(ALLOWED_TYPES)


def _render_edit_panel(node, tree_key):
    uid = node["uid"]
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input("Name", key=f"name_{tree_key}_{uid}")
        with c2:
            new_type = st.selectbox(
                "Type",
                options=_TYPE_OPTIONS,
                key=f"type_{tree_key}_{uid}",
                disabled=bool(node["children"]),
            )

        c3, c4, c5 = st.columns(3)
        with c3:
            new_min = st.number_input(
                "minOccurs", min_value=0, key=f"min_{tree_key}_{uid}"
            )
        with c4:
            unbounded = st.checkbox("unbounded", key=f"unb_{tree_key}_{uid}")
        with c5:
            if unbounded:
                new_max = "unbounded"
                st.text_input(
                    "maxOccurs", value="unbounded", disabled=True,
                    key=f"maxd_{tree_key}_{uid}",
                )
            else:
                max_key = f"max_{tree_key}_{uid}"
                if max_key not in st.session_state:
                    current_max = (
                        node["max_occurs"]
                        if isinstance(node["max_occurs"], int)
                        else 1
                    )
                    st.session_state[max_key] = current_max
                new_max = st.number_input(
                    "maxOccurs", min_value=1, key=max_key,
                )

        if st.button("Apply", key=f"apply_{tree_key}_{uid}", type="primary"):
            node["name"] = new_name
            node["type"] = new_type
            node["min_occurs"] = new_min
            node["max_occurs"] = new_max
            st.session_state.editing_uid = None
            st.session_state.editing_tree = None
            st.rerun()


def _render_tree(tree_key):
    tree = st.session_state[f"{tree_key}_tree"]

    if not tree:
        st.caption("No fields defined yet.")

    for node, depth in _flatten(tree):
        uid = node["uid"]
        margin = depth * 24

        is_editing = (
            st.session_state.editing_uid == uid
            and st.session_state.editing_tree == tree_key
        )

        if node["children"]:
            text = f"<b>{node['name']}</b> <code>[{node['min_occurs']}..{node['max_occurs']}]</code>"
        else:
            text = (
                f"<b>{node['name']}</b> : <code>{node['type']}</code>"
                f" <code>[{node['min_occurs']}..{node['max_occurs']}]</code>"
            )
        label = f'<div style="margin-left:{margin}px">{text}</div>'

        col_label, col_edit, col_child, col_updowndel = st.columns(
            [5, 1, 1, 2]
        )

        with col_label:
            st.markdown(label, unsafe_allow_html=True)

        with col_edit:
            if st.button(
                "Close" if is_editing else "Edit", key=f"e_{tree_key}_{uid}"
            ):
                if is_editing:
                    st.session_state.editing_uid = None
                    st.session_state.editing_tree = None
                else:
                    st.session_state.editing_uid = uid
                    st.session_state.editing_tree = tree_key
                    _reset_edit_keys(tree_key, uid, node)
                st.rerun()

        with col_child:
            if st.button("+Child", key=f"a_{tree_key}_{uid}"):
                node["children"].append(_new_node())
                st.rerun()

        with col_updowndel:
            bu, bd, bx = st.columns(3)
            if bu.button("⬆️", key=f"u_{tree_key}_{uid}"):
                _move_node(tree, uid, -1)
                st.rerun()
            if bd.button("⬇️", key=f"d_{tree_key}_{uid}"):
                _move_node(tree, uid, 1)
                st.rerun()
            if bx.button("🗑️", key=f"x_{tree_key}_{uid}"):
                if st.session_state.editing_uid == uid:
                    st.session_state.editing_uid = None
                    st.session_state.editing_tree = None
                _delete_node(tree, uid)
                st.rerun()

        if is_editing:
            _render_edit_panel(node, tree_key)

    if st.button("+ Add field", key=f"add_root_{tree_key}"):
        tree.append(_new_node())
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="SOAP Blueprint", layout="wide")
    _init_state()

    with open(_LOGO_PATH, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode()
    st.markdown(
        f'<h1><img src="data:image/png;base64,{logo_b64}" '
        'style="height:1em;vertical-align:middle;margin-right:0.3em">'
        'SOAP Blueprint</h1>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Build WSDL files to define your SOAP service schema. "
        "Validated for SAP services (ECC, S/4HANA, Integration Suite) and MuleSoft."
    )

    with st.sidebar:
        st.header("Service")
        service_name = st.text_input(
            "Service name", value="MyWebService", key="svc_name"
        )
        namespace_base = st.text_input(
            "Namespace base", value="http://example.com", key="ns_base"
        )
        st.subheader("Operation elements")
        request_element = st.text_input(
            "Request element", value="ZRequest", key="req_el"
        )
        response_element = st.text_input(
            "Response element", value="ZResponse", key="resp_el"
        )

    tab_req, tab_resp = st.tabs(["Request", "Response"])
    with tab_req:
        _render_tree("request")
    with tab_resp:
        _render_tree("response")

    st.divider()

    if st.button("Generate WSDL", type="primary"):
        try:
            validate_service_name(service_name)
            req_fields = _nodes_to_fields(st.session_state.request_tree)
            resp_fields = _nodes_to_fields(st.session_state.response_tree)
            for f in req_fields:
                validate_field(f)
            for f in resp_fields:
                validate_field(f)
            config = ServiceConfig(
                service_name=service_name,
                namespace_base=namespace_base,
                request_element=request_element,
                response_element=response_element,
            )
            st.session_state.generated_wsdl = generate_wsdl(
                config, req_fields, resp_fields
            )
            st.session_state.generated_xsd = generate_xsd(
                config, req_fields, resp_fields
            )
            st.session_state.sample_request = generate_sample_message(
                config, req_fields, request_element
            )
            st.session_state.sample_response = generate_sample_message(
                config, resp_fields, response_element
            )
            st.session_state.postman_collection = generate_postman_collection(
                config, req_fields
            )
        except ValidationError as e:
            st.error(str(e))
            st.session_state.generated_wsdl = None
            st.session_state.generated_xsd = None
            st.session_state.sample_request = None
            st.session_state.sample_response = None
            st.session_state.postman_collection = None

    if st.session_state.generated_wsdl:
        st.code(st.session_state.generated_wsdl, language="xml")

        # -- Button styling per group --
        st.markdown("""
        <style>
        div[data-testid="stColumn"]:has(button[kind="secondary"]) button {
            border-color: #ff6347;
            color: #ff6347;
        }
        </style>
        """, unsafe_allow_html=True)

        grp_dl, grp_ex, grp_pm = st.columns([2, 2, 1])

        with grp_dl:
            st.caption("Download")
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "WSDL",
                    icon=":material/download:",
                    data=st.session_state.generated_wsdl,
                    file_name=f"{service_name}.wsdl",
                    mime="application/xml",
                    type="primary",
                )
            with c2:
                st.download_button(
                    "XSD",
                    icon=":material/download:",
                    data=st.session_state.generated_xsd,
                    file_name=f"{service_name}.xsd",
                    mime="application/xml",
                    type="primary",
                )

        with grp_ex:
            st.caption("Examples")
            c3, c4 = st.columns(2)
            with c3:
                if st.button(
                    "Request",
                    icon=":material/visibility:",
                    key="show_sample_req",
                ):
                    if st.session_state.show_sample == "request":
                        st.session_state.show_sample = None
                    else:
                        st.session_state.show_sample = "request"
                    st.rerun()
            with c4:
                if st.button(
                    "Response",
                    icon=":material/visibility:",
                    key="show_sample_resp",
                ):
                    if st.session_state.show_sample == "response":
                        st.session_state.show_sample = None
                    else:
                        st.session_state.show_sample = "response"
                    st.rerun()

        with grp_pm:
            st.caption("Testing")
            st.download_button(
                "Postman",
                icon=":material/send:",
                data=st.session_state.postman_collection,
                file_name=f"{service_name}.postman_collection.json",
                mime="application/json",
            )

        if st.session_state.show_sample == "request":
            st.code(st.session_state.sample_request, language="xml")
        elif st.session_state.show_sample == "response":
            st.code(st.session_state.sample_response, language="xml")


if __name__ == "__main__":
    main()
    st.divider()
    from datetime import date
    st.caption(
        f"made by [Manuel Almagro](https://blog.almag.ro) 🌱 {date.today().year}"
    )
