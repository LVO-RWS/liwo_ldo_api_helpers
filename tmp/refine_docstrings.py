from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(r"C:\RWS\Git\liwo_ldo_api_helpers")
SKIP_DIRS = {".git", ".venv", "__pycache__", "output", "tmp"}


SPECIFIC_SUMMARIES = {
    "_caller_script_path": "Return the first caller path outside this helper module.",
    "_caller_script_stem": "Return the stem of the calling script outside this helper module.",
    "_script_stamp": "Return the cached timestamp for a script stem.",
    "_sheet_title": "Build a safe Excel sheet title.",
    "_fmt": "Format a value for console table output.",
    "main": "Run the script workflow and return an exit code.",
    "load_env_fallback": "Load environment variables from nearby .env files.",
    "get_base": "Return the configured base URL.",
    "get_liwo_base": "Return the configured LIWO base URL.",
    "get_token": "Return the configured LDO API token.",
    "make_session": "Create an authenticated requests session.",
    "output_dir": "Return the base output directory.",
    "output_file": "Return a timestamped output file path.",
    "output_run_dir": "Return a timestamped output directory.",
    "latest_run_file": "Return the latest output file from an earlier run.",
    "api_url": "Join a base URL and API path.",
    "write_json": "Write a JSON payload to disk.",
    "write_csv": "Write rows to a CSV file.",
    "write_excel_workbook": "Write worksheets to an Excel workbook.",
    "write_excel": "Write rows to a single-sheet Excel workbook.",
    "print_json_block": "Print a titled JSON block.",
    "print_table": "Print rows as a console table.",
    "cell_text": "Convert a value to display text.",
    "join_unique": "Join unique non-empty values into one string.",
    "meta_value": "Return the first non-empty metadata value for the given keys.",
    "to_float": "Convert a value to a float when possible.",
    "list_scenarios_page": "Fetch one page of scenarios from the LDO API.",
    "iter_scenarios": "Yield scenarios page by page from the LDO API.",
    "get_xml": "Fetch and parse an XML response.",
    "local_name": "Return the local name of an XML tag.",
    "ensure_geo_stack": "Ensure that the geospatial dependencies are available.",
    "make_ldo_session": "Create an authenticated LDO session and return it with the base URL.",
    "thread_local_ldo_session": "Return a thread-local LDO session for concurrent work.",
    "crossborder_output_base_dir": "Return the base output directory for cross-border runs.",
    "crossborder_run_dir": "Return the output directory for a cross-border run.",
    "crossborder_output_file": "Return an output file path for a cross-border run.",
    "latest_crossborder_run_dir": "Return the latest cross-border output directory for a producer script.",
    "latest_crossborder_file": "Return the latest named file from a cross-border producer script.",
    "download_gadm_shapefile": "Download and extract a GADM shapefile archive.",
    "download_all_scenarios_excel": "Download the official all-scenarios Excel export from LDO.",
    "read_export_metadata": "Read and normalize the compact metadata columns from the LDO export.",
    "read_country_layers": "Read the NL and DE boundary layers and project them to RD New.",
    "find_depth_tif_url": "Find the most relevant depth raster for a scenario.",
    "bounds_polygon_from_dataset": "Build a bounds polygon from an open raster dataset.",
    "bounds_polygon_from_tif_url": "Build a bounds polygon from a raster URL.",
    "depth_stats_in_dataset": "Count valid and positive raster pixels within a geometry from an open dataset.",
    "depth_stats_in_geom": "Count valid and positive raster pixels within a geometry from a raster URL.",
    "classify_scenario_for_de_crossborder": "Classify a scenario as DE-only, cross-border, or non-matching.",
    "download_file": "Download a remote file to disk.",
    "discover_workspaces": "Discover available workspaces from the LIWO service.",
    "count_layers": "Count layer elements in a capabilities document.",
    "sanitize_name": "Sanitize a name for use in file paths.",
    "build_wfs_url": "Build the WFS request URL for a layer.",
    "parse_layers_from_global_caps": "Parse scenario layers from the global LIWO capabilities document.",
    "fetch_ids": "Fetch coverage identifiers from a WCS capabilities response.",
    "choose_file_name": "Choose a safe local filename for a scenario file.",
    "to_row": "Convert a scenario payload to a compact row.",
    "in_bbox": "Return whether a point falls inside the configured bounding box.",
    "fetch_scenario_files": "Fetch and normalize file metadata for one scenario.",
    "value_type": "Return a readable type label for a value.",
    "collect_field_paths": "Collect flattened field paths from a nested payload.",
    "write_text_list": "Write a list of text lines to disk.",
    "mb": "Convert bytes to megabytes.",
    "_is_valid_xlsx": "Return whether a file looks like a valid Excel workbook.",
    "_pick": "Return the first non-empty value for the given keys.",
    "_api_file_size": "Return the file size reported by the API payload.",
    "_range_get_content_length": "Fetch the content length of a remote file with a range request.",
    "_map_file_to_column": "Map a file name to the matching output column.",
    "_short_error": "Compress an exception message for reporting.",
    "print_console_summary": "Print the file-size summary to the console.",
    "fetch_meta_and_sizes_row": "Fetch one scenario row with metadata and file size estimates.",
    "candidate_openapi_urls": "Return candidate OpenAPI endpoints to probe.",
    "fetch_openapi": "Fetch an OpenAPI document from the first working endpoint.",
    "resolve_ref": "Resolve a JSON schema reference in the OpenAPI document.",
    "flatten_schema": "Flatten a nested schema into printable field definitions.",
    "pick_response_schema": "Pick the most relevant response schema for an endpoint.",
    "schema_container_name": "Return a readable container name for a schema fragment.",
    "fetch_scenario_profile": "Fetch a representative scenario payload for schema inspection.",
    "print_endpoint_overview": "Print a compact endpoint overview.",
    "print_endpoint_fields": "Print flattened field definitions for selected endpoints.",
    "get_wms_text": "Fetch a WMS capabilities document as raw text.",
    "normalize_column_name": "Normalize a column name for comparison and export.",
    "parse_iso_datetime": "Parse an ISO-like datetime value when possible.",
    "same_nonempty_text": "Return whether two text values are equal and non-empty.",
    "bbox_center_epsg28992": "Return the center of a bounding box in EPSG:28992.",
    "grid_key": "Return a coarse grid key for spatial indexing.",
    "bouw_ldo_spatial_index": "Build a coarse spatial index for LDO scenarios.",
    "bepaal_referentiepunt": "Determine the reference point for spatial matching.",
    "vind_kandidaten_binnen_buffer": "Find candidate scenarios within the configured buffer.",
    "familie_match_flags": "Build family-match flags for candidate scenarios.",
    "is_candidate_nieuwer": "Return whether a candidate scenario is newer than the reference scenario.",
    "kies_nieuwste_candidate": "Choose the newest matching candidate scenario.",
    "get_meta_value": "Return a metadata value from a scenario payload.",
    "node_name": "Return a readable name for an AST node.",
}


SPECIFIC_RETURN_DESCRIPTIONS = {
    "_caller_script_path": "Path to the calling script, or `None` when no caller is found.",
    "_caller_script_stem": "Stem of the calling script.",
    "_script_stamp": "Timestamp string used in output paths.",
    "get_base": "Configured base URL.",
    "get_liwo_base": "Configured LIWO base URL.",
    "get_token": "Configured LDO API token.",
    "make_session": "Authenticated requests session.",
    "output_dir": "Base output directory.",
    "output_file": "Timestamped output file path.",
    "output_run_dir": "Timestamped output directory.",
    "latest_run_file": "Latest matching output file path.",
    "api_url": "Joined request URL.",
    "to_float": "Parsed float, or `None` when conversion fails.",
    "list_scenarios_page": "Scenario page payload with items and total count.",
    "make_ldo_session": "Tuple with the base URL and authenticated session.",
    "thread_local_ldo_session": "Thread-local authenticated session.",
    "crossborder_output_base_dir": "Base cross-border output directory.",
    "crossborder_run_dir": "Timestamped cross-border output directory.",
    "crossborder_output_file": "Cross-border output file path.",
    "latest_crossborder_run_dir": "Latest matching cross-border output directory.",
    "latest_crossborder_file": "Latest matching cross-border output file path.",
    "download_gadm_shapefile": "Directory containing the extracted GADM files.",
    "download_all_scenarios_excel": "Path to the downloaded Excel export.",
    "read_export_metadata": "Normalized metadata table.",
    "read_country_layers": "Tuple with the NL and DE boundary layers.",
    "find_depth_tif_url": "Tuple with the chosen raster name and download URL.",
    "bounds_polygon_from_dataset": "Bounds polygon in the target CRS.",
    "bounds_polygon_from_tif_url": "Bounds polygon in RD New.",
    "depth_stats_in_dataset": "Dictionary with valid and positive pixel counts.",
    "depth_stats_in_geom": "Dictionary with valid and positive pixel counts.",
    "classify_scenario_for_de_crossborder": "Classification result for one scenario.",
    "download_file": "Path to the downloaded file.",
    "parse_layers_from_global_caps": "Parsed scenario-layer rows.",
    "fetch_ids": "Coverage identifiers found in the capabilities response.",
    "choose_file_name": "Safe local filename.",
    "to_row": "Compact row for CSV export.",
    "in_bbox": "Whether the point falls inside the bounding box.",
    "fetch_scenario_files": "Scenario id, normalized file rows, and an error message.",
    "value_type": "Readable type label.",
    "collect_field_paths": "Flattened field-path rows.",
    "mb": "Size in megabytes.",
    "_is_valid_xlsx": "Whether the file looks like a valid Excel workbook.",
    "_pick": "First non-empty matching value.",
    "_api_file_size": "File size reported by the API, when available.",
    "_range_get_content_length": "Content length reported by the remote server.",
    "_map_file_to_column": "Matching output column name.",
    "_short_error": "Shortened error message.",
    "candidate_openapi_urls": "Candidate OpenAPI URLs to try.",
    "fetch_openapi": "Fetched OpenAPI document.",
    "resolve_ref": "Resolved schema fragment.",
    "flatten_schema": "Flattened schema rows.",
    "pick_response_schema": "Most relevant response schema.",
    "schema_container_name": "Readable container name.",
    "fetch_scenario_profile": "Representative scenario payload.",
    "get_wms_text": "Raw WMS capabilities XML.",
    "normalize_column_name": "Normalized column name.",
    "parse_iso_datetime": "Parsed datetime value, or `None`.",
    "same_nonempty_text": "Whether both text values are equal and non-empty.",
    "bbox_center_epsg28992": "Center point of the bounding box.",
    "grid_key": "Grid key used for spatial indexing.",
    "bouw_ldo_spatial_index": "Spatial index grouped by grid key.",
    "bepaal_referentiepunt": "Reference point used for matching.",
    "vind_kandidaten_binnen_buffer": "Candidate scenarios within the search buffer.",
    "familie_match_flags": "Match flags per family criterion.",
    "is_candidate_nieuwer": "Whether the candidate is newer.",
    "kies_nieuwste_candidate": "Newest matching candidate scenario.",
    "get_meta_value": "Requested metadata value.",
    "local_name": "Tag name without the namespace prefix.",
    "node_name": "Readable node name.",
}


PARAM_DESCRIPTIONS = {
    "archive": "Zip archive to read from.",
    "args": "Positional arguments passed through to this helper.",
    "array": "Array-like values to process.",
    "base": "Base service URL.",
    "base_url": "Base API URL.",
    "category": "Scenario category label.",
    "chunk": "Response chunk to process.",
    "columns": "Column definitions for console output.",
    "country_code": "Country code for the requested dataset.",
    "csv_path": "Path to the CSV file.",
    "dataset": "Open raster dataset to inspect.",
    "default": "Fallback value to use when no explicit value is available.",
    "de_geom": "Geometry for the German area of interest.",
    "depth_hint": "Text hint used to identify the depth raster.",
    "destination": "Destination path for the download.",
    "dirname": "Optional directory name for the output run.",
    "encoding": "Text encoding to use.",
    "errors": "Collected errors to report or write.",
    "executor": "Executor used for concurrent work.",
    "export_path": "Path to the exported Excel file.",
    "fieldnames": "Field names to write to CSV or Excel.",
    "file_info": "File metadata dictionary.",
    "file_meta": "Nested file metadata payload.",
    "file_name": "File name to inspect or write.",
    "filename": "File name to generate or resolve.",
    "files": "File metadata mapping to inspect.",
    "geom": "Geometry to test or clip against.",
    "geom_crs": "CRS of the provided geometry.",
    "gdf_de": "German boundary GeoDataFrame.",
    "gdf_nl": "Dutch boundary GeoDataFrame.",
    "handle": "Open file handle used for writing.",
    "headers": "Headers used for a request or table.",
    "idx": "Index of the dataset or item to process.",
    "item": "Scenario, layer, or metadata item to process.",
    "items": "Sequence of items to process.",
    "json_path": "Path to the JSON file.",
    "key": "Key used to look up or format a value.",
    "keys": "Candidate keys to try in order.",
    "kwargs": "Keyword arguments passed through to this helper.",
    "label": "Console or output label.",
    "limit": "Maximum number of items to request.",
    "max_rows": "Maximum number of rows to print.",
    "max_scenarios": "Maximum number of scenarios to process. Use `0` for all.",
    "meta": "Metadata dictionary to inspect.",
    "min_positive": "Minimum raster value counted as positive.",
    "min_positive_depth": "Minimum depth value counted as positive.",
    "min_positive_pixels": "Minimum number of positive pixels required for a match.",
    "mode_public": "Whether to request only public scenarios.",
    "name": "Name to sanitize or inspect.",
    "nl_geom": "Geometry for the Dutch area of interest.",
    "node": "AST node to inspect.",
    "offset": "Pagination offset.",
    "output_path": "Path where output should be written.",
    "params": "Query parameters for the request.",
    "parts": "Extra path parts appended to the base output directory.",
    "path": "Path to read from or write to.",
    "payload": "Payload to print, inspect, or write.",
    "precision": "Precision used while transforming geometry.",
    "producer_script_stem": "Script stem used to look up prior outputs.",
    "raw": "Raw value to parse.",
    "ref": "Schema reference to resolve.",
    "rel_filename": "Filename to look up in an earlier run.",
    "required": "Whether the function should fail when the value is missing.",
    "response": "HTTP response object to inspect.",
    "rows": "Rows to print or write.",
    "scenario": "Scenario payload to inspect.",
    "scenario_id": "Scenario identifier.",
    "scenario_ids": "Scenario identifiers to process.",
    "script_stem": "Script stem used to derive output paths.",
    "selected": "Already selected values to extend.",
    "session": "Authenticated requests session.",
    "sheet_name": "Worksheet name to create.",
    "sheets": "Worksheet definitions to write.",
    "source_name": "Source field or dataset name.",
    "status": "Status value to inspect or report.",
    "tag": "XML tag value.",
    "target": "Target object, CRS, or destination.",
    "target_crs": "CRS to convert bounds into.",
    "target_dir": "Directory where files should be stored.",
    "target_name": "Target field or dataset name.",
    "text": "Text value to inspect or format.",
    "timeout": "Timeout in seconds.",
    "timeout_sec": "Timeout in seconds for a script run.",
    "title": "Title shown in console output.",
    "token": "API token used for authentication.",
    "total": "Total count to report.",
    "url": "URL to request or inspect.",
    "used_titles": "Already used worksheet titles.",
    "value": "Value to inspect or convert.",
    "values": "Values to inspect or combine.",
    "version": "Version string for the requested service or dataset.",
    "wanted": "Requested keys or fields to keep.",
    "width": "Display width for console formatting.",
    "workbook": "Workbook instance to update.",
    "worksheet": "Worksheet instance to update.",
    "x": "X coordinate value.",
    "y": "Y coordinate value.",
}


ACTION_RETURN_PREFIXES = (
    "Return ",
    "Read ",
    "Load ",
    "Fetch ",
    "Build ",
    "Create ",
    "Download ",
    "Parse ",
    "Normalize ",
    "Collect ",
    "Count ",
    "Choose ",
    "Resolve ",
    "Flatten ",
    "Filter ",
    "Find ",
    "Determine ",
    "Discover ",
    "Map ",
    "Convert ",
    "Join ",
)


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def annotation_text(annotation: ast.expr | None) -> str:
    if annotation is None:
        return "Any"
    try:
        return ast.unparse(annotation)
    except Exception:
        return "Any"


def words_from_name(name: str) -> list[str]:
    return [word for word in name.strip("_").split("_") if word]


def title_phrase(text: str) -> str:
    text = text.strip().rstrip(".")
    if not text:
        return "Value"
    return text[:1].upper() + text[1:]


def summary_from_name(name: str) -> str:
    words = words_from_name(name)
    if not words:
        return "Return the requested value."

    first = words[0].lower()
    tail = " ".join(words[1:]) if len(words) > 1 else "value"
    verb_map = {
        "get": f"Return {tail}.",
        "load": f"Load {tail}.",
        "read": f"Read {tail}.",
        "write": f"Write {tail}.",
        "print": f"Print {tail}.",
        "fetch": f"Fetch {tail}.",
        "download": f"Download {tail}.",
        "build": f"Build {tail}.",
        "make": f"Build {tail}.",
        "create": f"Create {tail}.",
        "resolve": f"Resolve {tail}.",
        "pick": f"Select {tail}.",
        "flatten": f"Flatten {tail}.",
        "parse": f"Parse {tail}.",
        "normalize": f"Normalize {tail}.",
        "sanitize": f"Sanitize {tail}.",
        "discover": f"Discover {tail}.",
        "count": f"Count {tail}.",
        "choose": f"Choose {tail}.",
        "describe": f"Describe {tail}.",
        "decode": f"Decode {tail}.",
        "filter": f"Filter {tail}.",
        "iter": f"Yield {tail}.",
        "list": f"List {tail}.",
        "same": f"Return whether {tail}.",
        "is": f"Return whether {tail}.",
        "haal": f"Fetch {tail}.",
        "maak": f"Build {tail}.",
        "schrijf": f"Write {tail}.",
        "vind": f"Find {tail}.",
        "kies": f"Choose {tail}.",
        "bouw": f"Build {tail}.",
        "bepaal": f"Determine {tail}.",
        "tel": f"Count {tail}.",
    }
    if first in verb_map:
        return title_phrase(verb_map[first])
    return f"Return {tail}."


def summary_for(name: str) -> str:
    return SPECIFIC_SUMMARIES.get(name, summary_from_name(name))


def infer_return_type(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
        return annotation_text(node.returns)
    if any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node)):
        return "Iterator[Any]"
    returns = [child for child in ast.walk(node) if isinstance(child, ast.Return)]
    if not returns or all(ret.value is None for ret in returns):
        return "None"
    return "Any"


def return_from_summary(summary: str) -> str:
    text = summary.strip().rstrip(".")
    if " and return it with " in text:
        _, _, tail = text.partition(" and return it with ")
        prefix = text.split(" and return it with ", 1)[0]
        if prefix.lower().startswith("create "):
            thing = prefix[7:]
            return title_phrase(f"{thing} and {tail}")
    for prefix in ACTION_RETURN_PREFIXES:
        if text.startswith(prefix):
            return title_phrase(text[len(prefix):]) + "."
    if text.startswith("Yield "):
        return title_phrase(text[6:]) + "."
    return title_phrase(text) + "."


def return_description(name: str, return_type: str, summary: str) -> str:
    if name in SPECIFIC_RETURN_DESCRIPTIONS:
        return SPECIFIC_RETURN_DESCRIPTIONS[name]
    if return_type == "None":
        return "The function does not return a value."
    if return_type.startswith("Iterator"):
        return "Values yielded one by one."
    if return_type in {"bool", "Boolean"} or name.startswith(("is_", "same_")):
        return "Whether the requested condition is met."
    if return_type.startswith("tuple"):
        return return_from_summary(summary)
    if return_type.startswith("dict"):
        return return_from_summary(summary)
    if return_type.startswith("list"):
        return return_from_summary(summary)
    if "Path" in return_type or "path" in summary.lower() or "directory" in summary.lower():
        return return_from_summary(summary)
    if "Session" in return_type or "session" in summary.lower():
        return return_from_summary(summary)
    if return_type in {"str", "str | None"}:
        return return_from_summary(summary)
    if return_type in {"int", "float", "float | None"}:
        return return_from_summary(summary)
    return return_from_summary(summary)


def parameter_description(param_name: str) -> str:
    return PARAM_DESCRIPTIONS.get(param_name, f"Argument passed to `{param_name}`.")


def build_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    indent = " " * (node.col_offset + 4)
    body_indent = indent + "    "
    summary = summary_for(node.name)
    lines: list[str] = [f'{indent}"""{summary}', ""]

    all_args = list(node.args.posonlyargs) + list(node.args.args)
    if node.args.vararg is not None:
        all_args.append(node.args.vararg)
    all_args.extend(node.args.kwonlyargs)
    if node.args.kwarg is not None:
        all_args.append(node.args.kwarg)

    visible_args = [arg for arg in all_args if arg.arg != "self"]
    if visible_args:
        lines.extend([f"{indent}Parameters", f"{indent}----------"])
        for arg in visible_args:
            arg_name = arg.arg
            arg_type = annotation_text(arg.annotation)
            prefix = ""
            if node.args.vararg is arg:
                prefix = "*"
            elif node.args.kwarg is arg:
                prefix = "**"
            lines.append(f"{indent}{prefix}{arg_name} : {arg_type}")
            lines.append(f"{body_indent}{parameter_description(arg_name)}")
        lines.append("")

    return_type = infer_return_type(node)
    lines.extend([f"{indent}Returns", f"{indent}-------", f"{indent}{return_type}"])
    lines.append(f"{body_indent}{return_description(node.name, return_type, summary)}")
    lines.append(f'{indent}"""')
    return "\n".join(lines)


def replace_docstrings(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    lines = text.splitlines()
    updates: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = build_docstring(node)
        first_stmt = node.body[0]
        if (
            isinstance(first_stmt, ast.Expr)
            and isinstance(first_stmt.value, ast.Constant)
            and isinstance(first_stmt.value.value, str)
        ):
            start_line = first_stmt.lineno - 1
            end_line = first_stmt.end_lineno - 1
        else:
            start_line = first_stmt.lineno - 1
            end_line = start_line - 1
        updates.append((start_line, end_line, docstring))

    if not updates:
        return False

    for start_line, end_line, docstring in sorted(updates, key=lambda item: item[0], reverse=True):
        lines[start_line : end_line + 1] = docstring.splitlines()

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    changed = 0
    for path in sorted(ROOT.rglob("*.py")):
        if should_skip(path):
            continue
        changed += int(replace_docstrings(path))
    print(f"Updated {changed} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
