/**
 * Command injection detection for MCP tool call parameters.
 *
 * Screens the `command` parameter (and similar) in MCP tool calls for
 * shell injection patterns. The MCP STDIO transport executes a `command`
 * parameter verbatim, which Anthropic has confirmed is by design.
 * This module catches the injection at the proxy layer before it reaches
 * the server.
 *
 * Deterministic, no TI dependency. Mirrors the path traversal module's
 * structure: block on clear injection, flag on suspicious patterns.
 */

const COMMAND_PARAM_NAMES = new Set([
  "command", "cmd", "shell_command", "exec", "execute",
  "script", "code", "run",
]);

// Patterns that indicate shell command chaining or injection
const INJECTION_PATTERNS = [
  /;\s*\w/,              // semicolon followed by command
  /&&\s*\w/,             // && chaining
  /\|\|\s*\w/,           // || chaining
  /\|\s*\w/,             // pipe to command
  /`[^`]*`/,             // backtick execution
  /\$\([^)]*\)/,         // $(...) execution
  /\$\{[^}]*\}/,         // ${...} expansion
  />\s*\/dev\//,         // redirect to device
  /<\s*\/dev\//,         // read from device
  /\/bin\/(sh|bash|zsh|dash)/,  // explicit shell invocation
  /\/usr\/bin\/(sh|bash|env)/,
  /curl\s+.*\|\s*(sh|bash)/,    // curl pipe to shell
  /wget\s+.*\|\s*(sh|bash)/,    // wget pipe to shell
  /powershell\s+-[eE]nc/,       // powershell encoded command
  /cmd\.exe\s+\/c/i,
];

// Suspicious but not conclusive: flag for review
const SUSPICIOUS_PATTERNS = [
  /\bnc\s+-/,            // netcat with flags
  /\bncat\s/,            // ncat
  /\/tmp\/\w+\s+&/,      // background execution from tmp
  /chmod\s+\+x/,         // making executable
  /base64\s+-[dD]/,      // base64 decode
];

export const POISON_COMMAND_INJECTION = "command_injection";

/**
 * Check a single parameter value for command injection.
 * Returns { verdict: "block"|"flag"|"clean", confidence, reasons }.
 */
export function checkCommandParam(paramName, value) {
  if (typeof value !== "string") {
    return { verdict: "clean", confidence: 1.0, reasons: [] };
  }

  const lowerName = paramName.toLowerCase();
  if (!COMMAND_PARAM_NAMES.has(lowerName)) {
    return { verdict: "clean", confidence: 1.0, reasons: [] };
  }

  const reasons = [];

  for (const pattern of INJECTION_PATTERNS) {
    if (pattern.test(value)) {
      reasons.push(`injection_pattern:${pattern.source.slice(0, 30)}`);
    }
  }

  if (reasons.length > 0) {
    return {
      verdict: "block",
      confidence: 0.95,
      reasons,
      confidence_source: POISON_COMMAND_INJECTION,
    };
  }

  for (const pattern of SUSPICIOUS_PATTERNS) {
    if (pattern.test(value)) {
      reasons.push(`suspicious_pattern:${pattern.source.slice(0, 30)}`);
    }
  }

  if (reasons.length > 0) {
    return {
      verdict: "flag",
      confidence: 0.70,
      reasons,
      confidence_source: POISON_COMMAND_INJECTION,
    };
  }

  return { verdict: "clean", confidence: 1.0, reasons: [] };
}

/**
 * Screen all parameters of an MCP tool call.
 * Returns the worst verdict found.
 */
export function screenToolCall(toolName, params) {
  let worst = { verdict: "clean", confidence: 1.0, reasons: [] };

  if (!params || typeof params !== "object") {
    return worst;
  }

  for (const [name, value] of Object.entries(params)) {
    const result = checkCommandParam(name, value);
    if (result.verdict === "block") {
      return result; // short-circuit on block
    }
    if (result.verdict === "flag" && worst.verdict === "clean") {
      worst = result;
    }
  }

  return worst;
}
