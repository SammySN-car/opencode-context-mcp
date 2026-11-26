/**
 * OCCE v3 Sandboxed TypeScript Runner (Node v22+ V8 vm isolate)
 *
 * Reads a JSON request from stdin:
 *   { code: string, rpcUrl: string, token: string, timeoutMs?: number, maxOutputChars?: number }
 *
 * Strips TypeScript annotations using Node's built-in `stripTypeScriptTypes`,
 * then executes the snippet inside a locked-down `vm.Context` with NO `fs`,
 * NO `process`, NO `require`, NO `import`, and NO arbitrary `fetch`.
 * Only the `occe` RPC proxy and safe JS built-ins are exposed.
 */

import vm from "node:vm";
import { stripTypeScriptTypes } from "node:module";

const DEFAULT_TIMEOUT_MS = 60_000;
const MAX_TIMEOUT_MS = 300_000;
const DEFAULT_MAX_OUTPUT_CHARS = 16_000;
const MAX_LOG_CHARS = 4_000;

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf-8");
}

function createOcceClient(rpcUrl, token) {
  async function callRpc(method, args = {}) {
    const res = await fetch(rpcUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-OCCE-Token": token,
      },
      body: JSON.stringify({ method, arguments: args }),
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      throw new Error(`OCCE RPC error ${res.status}: ${errText}`);
    }
    return await res.json();
  }

  return Object.freeze({
    codeSkeleton: (opts) => callRpc("code_skeleton", opts),
    symbolSlice: (opts) => callRpc("symbol_slice", opts),
    fileSlice: (opts) => callRpc("file_slice", opts),
    smartExec: (opts) => callRpc("smart_exec", opts),
    testCompress: (opts) => callRpc("test_compress", opts),
    diffCompact: (opts = {}) => callRpc("diff_compact", opts),
    tokenLedger: () => callRpc("token_ledger", {}),
    sessionHandoff: () => callRpc("session_handoff", {}),
  });
}

function truncateText(text, maxChars) {
  if (text.length <= maxChars) return text;
  const omitted = text.length - maxChars;
  return text.slice(0, maxChars) + `\n... [OCCE CodeMode: ${omitted} chars truncated]`;
}

async function main() {
  const rawInput = await readStdin();
  const payload = JSON.parse(rawInput);

  const rawCode = String(payload.code || "");
  const rpcUrl = String(payload.rpcUrl || "");
  const token = String(payload.token || "");
  const timeoutMs = Math.min(
    Math.max(100, Number(payload.timeoutMs || DEFAULT_TIMEOUT_MS)),
    MAX_TIMEOUT_MS
  );
  const maxOutputChars = Math.max(500, Number(payload.maxOutputChars || DEFAULT_MAX_OUTPUT_CHARS));

  if (!rawCode.trim()) {
    process.stdout.write(JSON.stringify({ ok: false, error: "Empty code snippet", logs: [] }));
    return;
  }

  const logs = [];
  let logBytes = 0;
  function pushLog(level, args) {
    if (logBytes >= MAX_LOG_CHARS) return;
    const line = args
      .map((a) => (typeof a === "string" ? a : JSON.stringify(a)))
      .join(" ");
    const entry = level === "log" ? line : `[${level}] ${line}`;
    logBytes += entry.length;
    logs.push(entry);
  }

  // Strip TypeScript types inside an async wrapper so top-level `return` & `await` work
  const wrappedTs = `async function __occe_main__(occe: any) {\n${rawCode}\n}`;
  let strippedJs;
  try {
    strippedJs = stripTypeScriptTypes(wrappedTs, { mode: "strip" });
  } catch (err) {
    process.stdout.write(
      JSON.stringify({ ok: false, error: `TypeScript syntax error: ${err.message}`, logs: [] })
    );
    return;
  }

  const sandbox = Object.create(null);
  sandbox.occe = createOcceClient(rpcUrl, token);
  sandbox.console = Object.freeze({
    log: (...a) => pushLog("log", a),
    info: (...a) => pushLog("info", a),
    warn: (...a) => pushLog("warn", a),
    error: (...a) => pushLog("error", a),
  });
  sandbox.Promise = Promise;
  sandbox.JSON = JSON;
  sandbox.Math = Math;
  sandbox.Date = Date;
  sandbox.RegExp = RegExp;
  sandbox.Array = Array;
  sandbox.Object = Object;
  sandbox.Map = Map;
  sandbox.Set = Set;
  sandbox.Error = Error;
  sandbox.TypeError = TypeError;

  const context = vm.createContext(sandbox, {
    codeGeneration: { strings: false, wasm: false },
  });

  try {
    const fn = vm.runInContext(`(${strippedJs})`, context, {
      timeout: timeoutMs,
      filename: "occe-codemode-snippet.ts",
    });

    let timerId;
    const timeoutPromise = new Promise((_, reject) => {
      timerId = setTimeout(
        () => reject(new Error(`Execution timed out after ${timeoutMs}ms`)),
        timeoutMs
      );
      if (timerId.unref) timerId.unref();
    });

    const result = await Promise.race([fn(sandbox.occe), timeoutPromise]).finally(() =>
      clearTimeout(timerId)
    );
    const outPayload = {
      ok: true,
      result: result === undefined ? null : result,
      logs,
    };
    const serialized = truncateText(JSON.stringify(outPayload), maxOutputChars);
    process.stdout.write(serialized);
  } catch (err) {
    const errPayload = {
      ok: false,
      error: err && err.message ? err.message : String(err),
      logs,
    };
    process.stdout.write(truncateText(JSON.stringify(errPayload), maxOutputChars));
  }
}

main().catch((err) => {
  process.stdout.write(
    JSON.stringify({ ok: false, error: err && err.message ? err.message : String(err), logs: [] })
  );
  process.exit(1);
});
