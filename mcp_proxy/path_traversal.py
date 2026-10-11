"""Path traversal detection for MCP tool call parameters.

CVE-2025-68143/68144/68145 demonstrated that MCP servers (e.g.,
Anthropic's Git server) accept path parameters without validation.
A poisoned README instructs the assistant to pass traversal paths
like ../../etc or absolute paths like /home/user/.ssh, and the
server operates on them without checks. Combined with a filesystem
server, this yields code execution.

This module validates file/path parameters in MCP tool calls,
mirroring the SSRF URL validator's structure.
"""

import logging
import os
import re
import urllib.parse

log = logging.getLogger(__name__)

# Parameter names that likely carry filesystem paths (case-insensitive).
_PATH_PARAM_NAMES = {
    "repo_path", "path", "file_path", "filepath", "directory", "dir",
    "folder", "target", "source", "dest", "destination", "cwd",
    "working_dir", "workingdir", "root", "filename", "file",
}

# Traversal sequences in various encodings.
_TRAVERSAL_PATTERNS = [
    r"\.\./",           # ../
    r"\.\.\\",          # ..\
    r"%2e%2e%2f",       # URL-encoded ../
    r"%2e%2e%5c",       # URL-encoded ..\
    r"%252e%252e%252f", # double-encoded ../
    r"\.\.%2f",
    r"\.\.%5c",
    r"%c0%ae",          # overlong UTF-8 for .
]

# Null byte injection to truncate paths.
_NULL_BYTE_PATTERNS = [
    r"%00",
    r"\x00",
]

# Sensitive path fragments that warrant flagging even within workspace.
_SENSITIVE_PATTERNS = [
    ".ssh/", ".aws/", ".gnupg/", ".config/",
    ".env", "credentials", "secrets",
]

# Sensitive file extensions.
_SENSITIVE_EXTENSIONS = {
    ".pem", ".key", ".p12", ".pfx", ".jks",
}

# Sensitive exact filenames.
_SENSITIVE_FILENAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
}


def _decode_path(value: str) -> str:
    """Decode URL-encoded and double-encoded path for inspection."""
    decoded = value
    # Decode up to twice to catch double-encoding.
    for _ in range(2):
        new = urllib.parse.unquote(decoded)
        if new == decoded:
            break
        decoded = new
    return decoded


def _has_traversal(value: str) -> bool:
    """True if the value contains path traversal sequences."""
    decoded = _decode_path(value).lower()
    # Check for null bytes first.
    for pat in _NULL_BYTE_PATTERNS:
        if re.search(pat, decoded, re.IGNORECASE):
            return True
    for pat in _TRAVERSAL_PATTERNS:
        if re.search(pat, decoded, re.IGNORECASE):
            return True
    # Also check for .. segments after normalization.
    # Split on both separators and look for bare .. components.
    parts = re.split(r"[/\\]", decoded)
    if ".." in parts:
        return True
    return False


def _is_absolute_path(value: str) -> bool:
    """True for Unix or Windows absolute paths."""
    decoded = _decode_path(value)
    # Unix absolute.
    if decoded.startswith("/"):
        return True
    # Windows drive letter: C:\ or C:/
    if re.match(r"^[a-zA-Z]:[\\/]", decoded):
        return True
    # Windows UNC: \\server\share
    if decoded.startswith("\\\\"):
        return True
    return False


def _is_sensitive_path(value: str) -> list:
    """Return list of matched sensitive patterns, empty if none."""
    decoded = _decode_path(value).lower()
    matched = []
    for pat in _SENSITIVE_PATTERNS:
        if pat.lower() in decoded:
            matched.append(pat)
    # Check extensions.
    for ext in _SENSITIVE_EXTENSIONS:
        if decoded.endswith(ext):
            matched.append(f"*{ext}")
    # Check filenames.
    basename = decoded.replace("\\", "/").split("/")[-1]
    # Strip extension for filename check.
    name_no_ext = basename.rsplit(".", 1)[0] if "." in basename else basename
    if name_no_ext in _SENSITIVE_FILENAMES:
        matched.append(name_no_ext)
    return matched


def _canonical_within_root(value: str, workspace_root: str) -> bool:
    """True if the canonical path stays within workspace_root.

    Resolves symlinks and normalizes the path, then checks containment.
    Returns False on any resolution error (fail-closed for this check).
    """
    try:
        # Join with root if relative, then resolve.
        if _is_absolute_path(value):
            candidate = os.path.realpath(_decode_path(value))
        else:
            candidate = os.path.realpath(
                os.path.join(workspace_root, _decode_path(value))
            )
        root_real = os.path.realpath(workspace_root)
        # Ensure candidate is root or a descendant.
        return candidate == root_real or candidate.startswith(
            root_real + os.sep
        )
    except Exception as exc:
        log.warning("path canonicalization failed for %r: %s", value, exc)
        return False


def is_path_param(name: str, value) -> bool:
    """Heuristic: is this tool parameter a filesystem path?"""
    if not isinstance(value, str):
        return False
    if name.lower() in _PATH_PARAM_NAMES:
        return True
    # Value looks like a path even if the name doesn't match.
    v = value.strip()
    if "/" in v or "\\" in v or v.startswith("."):
        # Avoid false positives on URLs (handled by SSRF module).
        if v.startswith(("http://", "https://", "ftp://")):
            return False
        return True
    return False


class PathTraversalResult:
    """Result of path traversal screening."""

    def __init__(self, verdict="allow", reasons=None, param=None):
        self.verdict = verdict  # allow | flag | block
        self.reasons = reasons or []
        self.param = param

    def to_dict(self):
        return {
            "verdict": self.verdict,
            "reasons": self.reasons,
            "param": self.param,
        }


def screen_path_param(name: str, value: str, workspace_root: str = "/workspace",
                      allow_absolute: bool = False,
                      traversal_mode: str = "block",
                      sensitive_mode: str = "flag") -> PathTraversalResult:
    """Screen a single path parameter.

    Args:
        name: Parameter name.
        value: Parameter value (string).
        workspace_root: Canonical workspace root for containment checks.
        allow_absolute: If False, absolute paths are blocked/flagged.
        traversal_mode: "block", "flag", or "disabled" for traversal.
        sensitive_mode: "block", "flag", or "disabled" for sensitive paths.

    Returns:
        PathTraversalResult with verdict and reasons.
    """
    if not isinstance(value, str) or not value.strip():
        return PathTraversalResult("allow")

    reasons = []
    verdict = "allow"

    # 1. Traversal sequences -> block (or flag per mode).
    if traversal_mode != "disabled" and _has_traversal(value):
        reasons.append(f"traversal sequence in {name}")
        verdict = traversal_mode

    # 2. Absolute path outside workspace.
    if verdict == "allow" and _is_absolute_path(value):
        if not allow_absolute:
            if not _canonical_within_root(value, workspace_root):
                reasons.append(f"absolute path escapes workspace: {name}")
                verdict = traversal_mode if traversal_mode != "disabled" else "allow"
        # Even allowed absolute paths get canonical containment check.
        elif not _canonical_within_root(value, workspace_root):
            reasons.append(f"path escapes workspace root: {name}")
            verdict = traversal_mode if traversal_mode != "disabled" else "allow"

    # 3. Relative path escaping via canonicalization (symlink-aware).
    if verdict == "allow" and not _is_absolute_path(value):
        if not _canonical_within_root(value, workspace_root):
            reasons.append(f"path escapes workspace root: {name}")
            verdict = traversal_mode if traversal_mode != "disabled" else "allow"

    # 4. Sensitive patterns -> flag (or block per mode).
    if sensitive_mode != "disabled":
        sensitive = _is_sensitive_path(value)
        if sensitive:
            reasons.append(
                f"sensitive path pattern in {name}: {', '.join(sensitive)}"
            )
            # Sensitive flag doesn't override a block, but can upgrade allow->flag.
            if verdict == "allow":
                verdict = sensitive_mode

    return PathTraversalResult(verdict, reasons, param=name)


def screen_tool_paths(arguments: dict, workspace_root: str = "/workspace",
                      allow_absolute: bool = False,
                      traversal_mode: str = "block",
                      sensitive_mode: str = "flag") -> list:
    """Screen all path-like parameters in a tool call's arguments.

    Returns a list of PathTraversalResult for params that fired.
    Empty list means clean.
    """
    results = []
    if not isinstance(arguments, dict):
        return results
    for name, value in arguments.items():
        if is_path_param(name, value):
            r = screen_path_param(
                name, value,
                workspace_root=workspace_root,
                allow_absolute=allow_absolute,
                traversal_mode=traversal_mode,
                sensitive_mode=sensitive_mode,
            )
            if r.verdict != "allow":
                results.append(r)
    return results


# Poison category for firewall integration.
POISON_PATH_TRAVERSAL = "path_traversal"
