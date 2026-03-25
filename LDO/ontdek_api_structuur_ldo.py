#!/usr/bin/env python3
"""Ontdek de volledige LDO API-structuur met schema-velden.

Dit script toont:
1) endpoint-overzicht uit OpenAPI
2) alle response-velden per endpoint (zoals in legacy discover)
3) meta-sleutels + types voor een voorbeeldscenario
4) meta_data sleutels + types van external-processings van dat scenario
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import requests

from _ldo_common import (
    api_url,
    get_base,
    get_token,
    load_env_fallback,
    output_file,
    print_json_block,
    print_table,
    write_csv,
    write_json,
)

# Instellingen
BASE_URL = get_base()
TIMEOUT_SEC = 30
MAX_ENDPOINT_TABLE_ROWS = 0  # 0 = alles tonen
SCENARIO_ID_VOOR_META = 20022
TOON_ENDPOINT_VELDEN = True
MAX_ENDPOINTS_VOOR_VELD_PRINT = 0  # 0 = alles
TOON_VOLLEDIGE_SCENARIO_JSON = False
TOON_VOLLEDIGE_EXTERNAL_JSON = False


def candidate_openapi_urls(base: str) -> list[str]:
    """Build candidate OpenAPI URLs.

    Parameters
    ----------
    base : str
        Base URL for the request.

    Returns
    -------
    list[str]
        Collected items.
    """
    urls = [api_url(base, "openapi.json")]
    if "/api/v1" in base:
        root = base.split("/api/v1", 1)[0]
        urls.append(f"{root}/openapi.json")
    return list(dict.fromkeys(urls))


def fetch_openapi(base: str, token: str, timeout: int) -> tuple[str, dict]:
    """Fetch an OpenAPI document from a candidate URL.

    Parameters
    ----------
    base : str
        Base URL for the request.
    token : str
        Bearer token used for authenticated requests.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    tuple[str, dict]
        Tuple with the requested values.
    """
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    last_error: str = ""
    for url in candidate_openapi_urls(base):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return url, response.json()
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(f"Could not fetch OpenAPI. Last error: {last_error}")


def resolve_ref(ref: str, spec: dict) -> dict[str, Any]:
    """Resolve a `$ref` inside an OpenAPI document.

    Parameters
    ----------
    ref : str
        JSON reference string.
    spec : dict
        OpenAPI specification document.

    Returns
    -------
    dict[str, Any]
        Result dictionary.
    """
    node: Any = spec
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict):
            return {}
        node = node.get(part)
    return node if isinstance(node, dict) else {}


def flatten_schema(
    schema: Any,
    prefix: str,
    spec: dict,
    seen: set[str] | None = None,
) -> list[tuple[str, str]]:
    """Flatten a nested schema into field paths.

    Parameters
    ----------
    schema : Any
        Schema object to inspect.
    prefix : str
        Field prefix used while flattening.
    spec : dict
        OpenAPI specification document.
    seen : set[str] | None
        Set used to prevent recursive loops.

    Returns
    -------
    list[tuple[str, str]]
        Collected items.
    """
    if seen is None:
        seen = set()

    if not isinstance(schema, dict):
        return [(prefix, "<unknown>")]

    if "$ref" in schema:
        ref = str(schema.get("$ref", ""))
        if ref in seen:
            return []
        seen.add(ref)
        return flatten_schema(resolve_ref(ref, spec), prefix, spec, seen)

    fields: list[tuple[str, str]] = []

    if "oneOf" in schema and isinstance(schema.get("oneOf"), list):
        for sub in schema["oneOf"]:
            fields.extend(flatten_schema(sub, prefix, spec, seen))
        return fields
    if "anyOf" in schema and isinstance(schema.get("anyOf"), list):
        for sub in schema["anyOf"]:
            fields.extend(flatten_schema(sub, prefix, spec, seen))
        return fields
    if "allOf" in schema and isinstance(schema.get("allOf"), list):
        for sub in schema["allOf"]:
            fields.extend(flatten_schema(sub, prefix, spec, seen))
        return fields

    if schema.get("type") == "array":
        items = schema.get("items")
        if items is None:
            return [(f"{prefix}[]", "array")]
        return flatten_schema(items, f"{prefix}[]", spec, seen)

    if schema.get("type") == "object":
        props = schema.get("properties", {})
        if isinstance(props, dict) and props:
            for key, sub in props.items():
                fields.extend(flatten_schema(sub, f"{prefix}.{key}", spec, seen))
        additional = schema.get("additionalProperties")
        if additional is not None:
            fields.extend(flatten_schema(additional, f"{prefix}.<key>", spec, seen))
        if fields:
            return fields
        return [(prefix, "object")]

    dtype = str(schema.get("type") or schema.get("format") or "<unknown>")
    return [(prefix, dtype)]


def pick_response_schema(op: dict[str, Any]) -> Any:
    """Pick the preferred response schema for an operation.

    Parameters
    ----------
    op : dict[str, Any]
        OpenAPI operation object.

    Returns
    -------
    Any
        Preferred response schema, if one was found.
    """
    responses = op.get("responses", {})
    if not isinstance(responses, dict):
        return None
    preferred = ["200", "201", "202", "203", "204", "default"]
    ordered = preferred + [k for k in responses.keys() if k not in preferred]

    for code in ordered:
        resp = responses.get(code)
        if not isinstance(resp, dict):
            continue
        content = resp.get("content", {})
        if not isinstance(content, dict):
            continue
        app_json = content.get("application/json")
        if isinstance(app_json, dict) and "schema" in app_json:
            return app_json.get("schema")
        for media in content.values():
            if isinstance(media, dict) and "schema" in media:
                return media.get("schema")
    return None


def schema_container_name(schema: Any, method: str, path: str) -> str:
    """Return the schema container name for an endpoint.

    Parameters
    ----------
    schema : Any
        Schema object to inspect.
    method : str
        HTTP method name.
    path : str
        Target path for this operation.

    Returns
    -------
    str
        Text result.
    """
    if isinstance(schema, dict):
        if "$ref" in schema:
            return str(schema.get("$ref", "")).split("/")[-1] or f"{method} {path}"
        if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
            item = schema["items"]
            if "$ref" in item:
                return str(item.get("$ref", "")).split("/")[-1] + "[]"
    return f"{method} {path}"


def fetch_scenario_profile(
    base: str,
    token: str,
    scenario_id: int,
    timeout: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    """Fetch a representative scenario payload for schema discovery.

    Parameters
    ----------
    base : str
        Base URL for the request.
    token : str
        Bearer token used for authenticated requests.
    scenario_id : int
        Scenario identifier.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], list[dict[str, str]]]
        Tuple with the requested values.
    """
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    scen_resp = requests.get(
        api_url(base, f"scenarios/{scenario_id}"),
        headers=headers,
        timeout=timeout,
    )
    scen_resp.raise_for_status()
    scenario_payload = scen_resp.json()

    ext_resp = requests.get(
        api_url(base, f"scenarios/{scenario_id}/external-processings"),
        headers=headers,
        params={"limit": 200, "offset": 0},
        timeout=timeout,
    )
    ext_resp.raise_for_status()
    external_payload = ext_resp.json()

    meta = scenario_payload.get("meta", {}) if isinstance(scenario_payload, dict) else {}
    meta_rows: list[dict[str, str]] = []
    if isinstance(meta, dict):
        for key in sorted(meta.keys(), key=lambda k: str(k).lower()):
            value = meta.get(key)
            meta_rows.append(
                {
                    "meta_key": str(key),
                    "value_type": type(value).__name__,
                    "example": str(value)[:120],
                }
            )

    ext_type_counter: Counter[str] = Counter()
    ext_meta_type_map: defaultdict[str, set[str]] = defaultdict(set)
    items = (
        external_payload.get("items", [])
        if isinstance(external_payload, dict)
        and isinstance(external_payload.get("items"), list)
        else []
    )
    for item in items:
        if not isinstance(item, dict):
            continue
        ext_type_counter[str(item.get("type", ""))] += 1
        meta_data = item.get("meta_data", {}) if isinstance(item.get("meta_data"), dict) else {}
        for key, value in meta_data.items():
            ext_meta_type_map[str(key)].add(type(value).__name__)

    ext_meta_rows = [
        {
            "meta_data_key": key,
            "value_types": ",".join(sorted(types)),
        }
        for key, types in sorted(ext_meta_type_map.items(), key=lambda kv: kv[0].lower())
    ]

    return scenario_payload, external_payload, meta_rows, ext_meta_rows


def print_endpoint_overview(source_url: str, openapi: dict, rows: list[dict[str, str]]) -> None:
    """Print endpoint overview.

    Parameters
    ----------
    source_url : str
        Source URL to inspect.
    openapi : dict
        Parsed OpenAPI document.
    rows : list[dict[str, str]]
        Rows to write or print.
    """
    info = openapi.get("info", {}) if isinstance(openapi, dict) else {}
    method_counts = Counter(row["method"] for row in rows)
    tag_counts: Counter[str] = Counter()
    for row in rows:
        tags = [t.strip() for t in str(row.get("tags", "")).split(",") if t.strip()]
        if not tags:
            tag_counts["(geen tag)"] += 1
        for tag in tags:
            tag_counts[tag] += 1

    print_json_block(
        "OpenAPI samenvatting:",
        {
            "source_url": source_url,
            "title": info.get("title", ""),
            "version": info.get("version", ""),
            "endpoint_count": len(rows),
            "method_counts": dict(method_counts),
            "top_tags": dict(tag_counts.most_common(20)),
        },
    )
    print("")
    print("Endpoint overzicht:")
    print_table(
        rows,
        [
            ("method", "method", 6),
            ("path", "path", 70),
            ("operation_id", "operation_id", 35),
            ("tags", "tags", 30),
            ("summary", "summary", 60),
        ],
        MAX_ENDPOINT_TABLE_ROWS,
    )


def print_endpoint_fields(grouped_fields: dict[tuple[str, str], list[dict[str, str]]]) -> None:
    """Print endpoint fields.

    Parameters
    ----------
    grouped_fields : dict[tuple[str, str], list[dict[str, str]]]
        Grouped fields collected from the API schema.
    """
    print("")
    print("Response-velden per endpoint:")
    keys = sorted(grouped_fields.keys(), key=lambda k: (k[1], k[0]))
    if MAX_ENDPOINTS_VOOR_VELD_PRINT > 0:
        keys = keys[:MAX_ENDPOINTS_VOOR_VELD_PRINT]
    for method, path in keys:
        print("")
        print(f"{method:<6} {path}")
        print("  -> velden:")
        rows = sorted(grouped_fields[(method, path)], key=lambda r: r["field_path"])
        for row in rows:
            print(f"    - {row['field_path']} ({row['field_type']})")


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()
    token = get_token(required=True)

    print("1) OpenAPI-specificatie ophalen...")
    source_url, openapi = fetch_openapi(BASE_URL, token, TIMEOUT_SEC)
    paths = openapi.get("paths", {}) if isinstance(openapi, dict) else {}

    endpoint_rows: list[dict[str, str]] = []
    endpoint_field_rows: list[dict[str, str]] = []
    grouped_fields: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(op, dict):
                continue
            tags = op.get("tags", [])
            method_u = method.upper()
            row = {
                "method": method_u,
                "path": str(path),
                "operation_id": str(op.get("operationId", "")),
                "summary": str(op.get("summary", "")),
                "tags": ",".join(str(t) for t in tags) if isinstance(tags, list) else "",
            }
            endpoint_rows.append(row)

            schema = pick_response_schema(op)
            if schema is None:
                continue
            container = schema_container_name(schema, method_u, str(path))
            flat = flatten_schema(schema, container, openapi)
            for field_path, field_type in sorted(set(flat)):
                item = {
                    "method": method_u,
                    "path": str(path),
                    "operation_id": str(op.get("operationId", "")),
                    "field_path": field_path,
                    "field_type": field_type,
                }
                endpoint_field_rows.append(item)
                grouped_fields[(method_u, str(path))].append(item)

    endpoint_rows = sorted(endpoint_rows, key=lambda r: (r["path"], r["method"]))
    endpoint_field_rows = sorted(
        endpoint_field_rows, key=lambda r: (r["path"], r["method"], r["field_path"])
    )

    print(f"   OpenAPI geladen. Endpoint-count: {len(endpoint_rows)}")
    print("")
    print("2) Scenario metadata-profiel ophalen...")
    (
        scenario_payload,
        external_payload,
        scenario_meta_rows,
        external_meta_rows,
    ) = fetch_scenario_profile(BASE_URL, token, SCENARIO_ID_VOOR_META, TIMEOUT_SEC)
    print(f"   Scenario {SCENARIO_ID_VOOR_META}: {len(scenario_meta_rows)} meta-sleutels")
    print(
        f"   Scenario {SCENARIO_ID_VOOR_META}: {len(external_meta_rows)} external meta_data sleutels"
    )

    raw_path = output_file("ldo_openapi_raw.json")
    endpoint_path = output_file("ldo_openapi_endpoints.csv")
    endpoint_fields_path = output_file("ldo_openapi_endpoint_fields.csv")
    scenario_meta_types_path = output_file(f"scenario_{SCENARIO_ID_VOOR_META}_meta_types.csv")
    external_meta_types_path = output_file(
        f"scenario_{SCENARIO_ID_VOOR_META}_external_meta_types.csv"
    )
    scenario_json_path = output_file(f"scenario_{SCENARIO_ID_VOOR_META}.json")
    scenario_external_json_path = output_file(
        f"scenario_{SCENARIO_ID_VOOR_META}_external_processings.json"
    )
    meta_path = output_file("ldo_openapi_meta.json")

    write_json(raw_path, openapi)
    write_csv(
        endpoint_path,
        endpoint_rows,
        ["method", "path", "operation_id", "summary", "tags"],
    )
    write_csv(
        endpoint_fields_path,
        endpoint_field_rows,
        ["method", "path", "operation_id", "field_path", "field_type"],
    )
    write_csv(
        scenario_meta_types_path,
        scenario_meta_rows,
        ["meta_key", "value_type", "example"],
    )
    write_csv(
        external_meta_types_path,
        external_meta_rows,
        ["meta_data_key", "value_types"],
    )
    write_json(scenario_json_path, scenario_payload)
    write_json(scenario_external_json_path, external_payload)
    write_json(
        meta_path,
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_url": source_url,
            "endpoint_count": len(endpoint_rows),
            "endpoint_field_rows": len(endpoint_field_rows),
            "scenario_id_for_meta": SCENARIO_ID_VOOR_META,
            "scenario_meta_keys": len(scenario_meta_rows),
            "external_meta_keys": len(external_meta_rows),
        },
    )

    print("")
    print("3) Console-overzicht")
    print_endpoint_overview(source_url, openapi, endpoint_rows)
    print("")
    print(f"Meta-sleutels voor scenario {SCENARIO_ID_VOOR_META}:")
    print_table(
        scenario_meta_rows,
        [("meta_key", "meta_key", 45), ("value_type", "type", 12), ("example", "example", 65)],
        0,
    )
    print("")
    print(f"External meta_data sleutels voor scenario {SCENARIO_ID_VOOR_META}:")
    print_table(
        external_meta_rows,
        [("meta_data_key", "meta_data_key", 40), ("value_types", "value_types", 25)],
        0,
    )
    if TOON_ENDPOINT_VELDEN:
        print_endpoint_fields(grouped_fields)

    if TOON_VOLLEDIGE_SCENARIO_JSON:
        print("")
        print_json_block("Volledige scenario JSON:", scenario_payload)
    if TOON_VOLLEDIGE_EXTERNAL_JSON:
        print("")
        print_json_block("Volledige external-processings JSON:", external_payload)

    print("")
    print(f"Wrote: {raw_path}")
    print(f"Wrote: {endpoint_path}")
    print(f"Wrote: {endpoint_fields_path}")
    print(f"Wrote: {scenario_meta_types_path}")
    print(f"Wrote: {external_meta_types_path}")
    print(f"Wrote: {scenario_json_path}")
    print(f"Wrote: {scenario_external_json_path}")
    print(f"Wrote: {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
