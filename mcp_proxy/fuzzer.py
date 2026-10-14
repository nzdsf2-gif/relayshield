"""
Fuzzing mode for MCP pre-deployment scanner.
Sends malformed arguments to each tool to test server-side validation.
"""

import json
import urllib.request
from typing import Dict, Any, List


# Fuzzing payloads by category
FUZZ_PAYLOADS = {
    "type_confusion": [
        "string_instead_of_number",
        12345,  # number instead of string
        ["array", "instead", "of", "object"],
        {"object": "instead_of_string"},
        True,
        None,
    ],
    "boundary": [
        "",  # empty string
        "A" * 10240,  # 10KB string
        -1,
        0,
        999999999999,
        float("inf"),
    ],
    "injection": [
        "../etc/passwd",
        "../../..",
        "http://169.254.169.254/latest/meta-data/",
        "${7*7}",
        "{{7*7}}",
        "<script>alert(1)</script>",
        "'; DROP TABLE tools; --",
    ],
    "malformed": [
        "\x00\x01\x02",  # null bytes
        "\ud800",  # lone surrogate
    ],
}


def generate_fuzz_cases(tool_def: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate fuzz test cases for a tool based on its inputSchema.
    Returns list of {"name": str, "arguments": dict, "category": str}.
    """
    cases = []
    schema = tool_def.get("inputSchema", {})
    properties = schema.get("properties", {})
    tool_name = tool_def.get("name", "unknown")
    
    # If no properties, generate generic cases
    if not properties:
        for category, payloads in FUZZ_PAYLOADS.items():
            for i, payload in enumerate(payloads):
                cases.append({
                    "name": f"{tool_name}_generic_{category}_{i}",
                    "arguments": {"fuzz_input": payload},
                    "category": category,
                })
        return cases
    
    # Generate per-field cases
    for field_name, field_schema in properties.items():
        field_type = field_schema.get("type", "string")
        
        # Type confusion: send wrong types
        wrong_types = {
            "string": [123, True, [], {}],
            "number": ["not_a_number", True, [], {}],
            "integer": ["not_an_int", 3.14, True, []],
            "boolean": ["not_a_bool", 123, [], {}],
            "array": ["not_an_array", 123, {}, True],
            "object": ["not_an_object", 123, [], True],
        }
        for wrong in wrong_types.get(field_type, []):
            cases.append({
                "name": f"{tool_name}_{field_name}_type_confusion",
                "arguments": {field_name: wrong},
                "category": "type_confusion",
            })
        
        # Injection probes (for string fields)
        if field_type == "string":
            for payload in FUZZ_PAYLOADS["injection"]:
                cases.append({
                    "name": f"{tool_name}_{field_name}_injection",
                    "arguments": {field_name: payload},
                    "category": "injection",
                })
        
        # Boundary values
        for payload in FUZZ_PAYLOADS["boundary"]:
            cases.append({
                "name": f"{tool_name}_{field_name}_boundary",
                "arguments": {field_name: payload},
                "category": "boundary",
            })
    
    # Missing required fields
    required = schema.get("required", [])
    if required:
        cases.append({
            "name": f"{tool_name}_missing_required",
            "arguments": {},
            "category": "schema_violation",
        })
    
    return cases


def run_fuzz_test(url: str, tool_name: str, arguments: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
    """
    Send a single fuzz test to the server.
    Returns {"status": "PASS|WARN|FAIL|CRITICAL", "detail": str}.
    """
    req_data = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }).encode('utf-8')
    
    req = urllib.request.Request(
        url, data=req_data,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            result = json.loads(body)
            
            # Check for error response (good - server rejected invalid input)
            if "error" in result:
                return {"status": "PASS", "detail": "Server properly rejected with JSON-RPC error"}
            
            # Check for suspicious indicators in response
            body_lower = body.lower()
            if any(ind in body_lower for ind in ["root:", "/etc/passwd", "stack trace", "traceback"]):
                return {"status": "CRITICAL", "detail": "Response contains suspicious system data"}
            
            # Server accepted invalid input
            return {"status": "WARN", "detail": "Server accepted malformed input without error"}
            
    except urllib.error.HTTPError as e:
        # HTTP error is actually good - server rejected
        if e.code in (400, 422):
            return {"status": "PASS", "detail": f"Server returned HTTP {e.code}"}
        return {"status": "FAIL", "detail": f"Unexpected HTTP {e.code}"}
    except Exception as e:
        return {"status": "FAIL", "detail": f"Request failed: {str(e)[:200]}"}


def fuzz_tool(url: str, tool_def: Dict[str, Any], max_cases: int = 50) -> Dict[str, Any]:
    """
    Fuzz a single tool and return aggregated results.
    """
    tool_name = tool_def.get("name", "unknown")
    cases = generate_fuzz_cases(tool_def)[:max_cases]
    
    results = {"tool": tool_name, "total": len(cases), "passed": 0, "warnings": 0, "failures": 0, "critical": 0, "details": []}
    
    for case in cases:
        outcome = run_fuzz_test(url, tool_name, case["arguments"])
        status = outcome["status"]
        
        if status == "PASS":
            results["passed"] += 1
        elif status == "WARN":
            results["warnings"] += 1
        elif status == "FAIL":
            results["failures"] += 1
        elif status == "CRITICAL":
            results["critical"] += 1
        
        if status in ("FAIL", "CRITICAL"):
            results["details"].append({
                "test": case["name"],
                "category": case["category"],
                "status": status,
                "detail": outcome["detail"],
            })
    
    return results
