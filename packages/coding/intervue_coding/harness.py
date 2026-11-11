"""Test-harness programs that run *inside* the sandbox.

The harness receives only test arguments (never expected outputs), calls the candidate's
function, and prints one marker-prefixed JSON line with the actual return values. Everything is
delivered over stdin, so the sandbox needs no bind mounts.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

LANG_EXT = {"python": "py", "javascript": "mjs", "typescript": "ts"}

PY_RUNNER = r"""
import contextlib, io, json, sys, time, traceback
sys.path.insert(0, WORKDIR)
sys.setrecursionlimit(5000)
def _conv(o):
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=repr)
    if isinstance(o, tuple):
        return list(o)
    return repr(o)
def _emit(obj):
    sys.__stdout__.write(MARK + json.dumps(obj, default=_conv) + "\n")
    sys.__stdout__.flush()
data = json.loads(open(WORKDIR + "/input.json").read())
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        import solution
    fn = getattr(solution, data["function"])
except Exception as e:
    _emit({"fatal": "".join(traceback.format_exception_only(type(e), e)).strip()[-1500:], "stdout": buf.getvalue()[-4000:]})
    sys.exit(0)
results = []
for t in data["tests"]:
    buf = io.StringIO()
    start = time.perf_counter()
    try:
        with contextlib.redirect_stdout(buf):
            val = fn(*t["args"])
        json.dumps(val, default=_conv)
        results.append({"name": t["name"], "ok": True, "value": val, "stdout": buf.getvalue()[-2000:], "ms": int((time.perf_counter()-start)*1000)})
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        line = next((f.lineno for f in reversed(tb) if f.filename.endswith("solution.py")), None)
        msg = "".join(traceback.format_exception_only(type(e), e)).strip()
        results.append({"name": t["name"], "ok": False, "error": (f"line {line}: " if line else "") + msg[-800:], "stdout": buf.getvalue()[-2000:], "ms": int((time.perf_counter()-start)*1000)})
_emit({"results": results})
"""

JS_RUNNER = r"""
import fs from "node:fs";
import { pathToFileURL } from "node:url";
const data = JSON.parse(fs.readFileSync(WORKDIR + "/input.json", "utf8"));
const emit = (o) => process.stdout.write(MARK + JSON.stringify(o) + "\n");
let captured = [];
const fmt = (args) => args.map((a) => (typeof a === "string" ? a : JSON.stringify(a))).join(" ");
console.log = (...a) => { captured.push(fmt(a)); };
console.error = (...a) => { captured.push(fmt(a)); };
let fn;
try {
  const mod = await import(pathToFileURL(WORKDIR + "/solution." + data.ext).href);
  fn = mod[data.function] ?? mod.default;
  if (typeof fn !== "function") throw new Error(`Function ${data.function} is not exported`);
} catch (e) {
  emit({ fatal: String((e && e.message) || e).slice(0, 1500), stdout: captured.join("\n").slice(-4000) });
  process.exit(0);
}
const results = [];
for (const t of data.tests) {
  captured = [];
  const start = performance.now();
  try {
    let val = fn(...t.args);
    if (val && typeof val.then === "function") val = await val;
    results.push({ name: t.name, ok: true, value: val === undefined ? null : val, stdout: captured.join("\n").slice(-2000), ms: Math.round(performance.now() - start) });
  } catch (e) {
    results.push({ name: t.name, ok: false, error: String((e && e.message) || e).slice(0, 800), stdout: captured.join("\n").slice(-2000), ms: Math.round(performance.now() - start) });
  }
}
emit({ results });
"""


def build_payload(language: str, code: str, function_name: str, tests: list[dict[str, Any]], workdir: str) -> tuple[dict[str, str], str]:
    """Return (files, marker). Files are written into `workdir` inside the sandbox."""
    if language not in LANG_EXT:
        raise ValueError(f"Unsupported language: {language}")
    marker = f"__INTERVUE_RESULT_{secrets.token_hex(8)}__"
    ext = LANG_EXT[language]
    data = {"function": function_name, "tests": [{"name": t["name"], "args": t["args"]} for t in tests], "ext": ext}
    header = f"WORKDIR = {json.dumps(workdir)}\nMARK = {json.dumps(marker)}\n"
    if language == "python":
        runner_name, runner = "runner.py", header + PY_RUNNER
    else:
        js_header = f"const WORKDIR = {json.dumps(workdir)};\nconst MARK = {json.dumps(marker)};\n"
        runner_name, runner = "runner.mjs", js_header + JS_RUNNER
    files = {f"solution.{ext}": code, runner_name: runner, "input.json": json.dumps(data)}
    return files, marker


def parse_output(stdout: str, marker: str) -> tuple[dict[str, Any] | None, str]:
    """Split sandbox stdout into (marker payload, remaining program output)."""
    payload = None
    other: list[str] = []
    for line in stdout.splitlines():
        if line.startswith(marker):
            try:
                payload = json.loads(line[len(marker) :])
            except json.JSONDecodeError:
                payload = None
        else:
            other.append(line)
    return payload, "\n".join(other)[-8000:]
