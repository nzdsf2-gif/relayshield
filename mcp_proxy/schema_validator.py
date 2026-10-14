"""
Argument Schema Validation for MCP Proxy Firewall.
Validates tool call arguments against the tool's declared JSON Schema
before forwarding to the upstream server.
"""

import json
from typing import Dict, Any, Tuple, List


class SchemaValidationError(Exception):
    """Raised when arguments fail schema validation."""
    def __init__(self, tool: str, violations: List[Dict[str, str]]):
        self.tool = tool
        self.violations = violations
        super().__init__(f"Schema validation failed for {tool}: {violations}")


def validate_arguments(tool_name: str, arguments: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
    """
    Validate arguments against a JSON Schema.
    Returns (is_valid, violations).
    Each violation is {"severity": "CRITICAL|HIGH|MEDIUM|LOW", "field": str, "message": str}.
    """
    violations = []
    
    if not schema:
        return True, []
    
    # Check type
    schema_type = schema.get("type", "object")
    if schema_type == "object" and not isinstance(arguments, dict):
        violations.append({
            "severity": "CRITICAL",
            "field": "",
            "message": f"Expected object, got {type(arguments).__name__}"
        })
        return False, violations
    
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    # Check required fields
    for field in required:
        if field not in arguments:
            violations.append({
                "severity": "HIGH",
                "field": field,
                "message": f"Missing required field: {field}"
            })
    
    # Check each provided argument
    for key, value in arguments.items():
        if key not in properties:
            # Additional properties - warn but don't block by default
            violations.append({
                "severity": "LOW",
                "field": key,
                "message": f"Unexpected field not in schema: {key}"
            })
            continue
        
        prop_schema = properties[key]
        expected_type = prop_schema.get("type")
        
        if expected_type:
            actual_type = _json_type(value)
            if actual_type != expected_type:
                # Allow int where number expected
                if not (expected_type == "number" and actual_type == "integer"):
                    violations.append({
                        "severity": "MEDIUM",
                        "field": key,
                        "message": f"Type mismatch for '{key}': expected {expected_type}, got {actual_type}"
                    })
        
        # Check enum
        enum_values = prop_schema.get("enum")
        if enum_values and value not in enum_values:
            violations.append({
                "severity": "MEDIUM",
                "field": key,
                "message": f"Value '{value}' not in allowed enum: {enum_values}"
            })
        
        # Check nested objects recursively
        if expected_type == "object" and isinstance(value, dict):
            nested_valid, nested_violations = validate_arguments(
                f"{tool_name}.{key}", value, prop_schema
            )
            violations.extend(nested_violations)
    
    # Determine if blocking (HIGH or CRITICAL violations)
    is_valid = not any(v["severity"] in ("HIGH", "CRITICAL") for v in violations)
    return is_valid, violations


def _json_type(value: Any) -> str:
    """Map Python type to JSON Schema type name."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


class SchemaStore:
    """In-memory store of tool schemas from tools/list."""
    
    def __init__(self):
        self._schemas: Dict[str, Dict[str, Any]] = {}
    
    def update_from_tools_list(self, tools: List[Dict[str, Any]]):
        """Store schemas from a tools/list response."""
        for tool in tools:
            name = tool.get("name")
            schema = tool.get("inputSchema", {})
            if name:
                self._schemas[name] = schema
    
    def get_schema(self, tool_name: str) -> Dict[str, Any]:
        """Get the schema for a tool, or empty dict if unknown."""
        return self._schemas.get(tool_name, {})
    
    def has_schema(self, tool_name: str) -> bool:
        return tool_name in self._schemas
