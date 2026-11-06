// OpenCode Context Engine (OCCE) Companion Hook Plugin
// Automatically optimizes built-in tool outputs to preserve token budget in OpenCode 2.x

const ANSI_REGEX = /(?:\x1B[@-Z\\-_]|[\x80-\x9A\x9C-\x9F]|(?:\x1B\[|\x9B)[0-?]*[ -/]*[@-~])/g;

// Deduplication set to ensure steering prompt is injected only once per request
const handledEvents = (globalThis.__occeSteeringHandled ??= new WeakSet());

// Track sessions that have received a shell-read reminder to avoid terminal clutter
const remindedSessions = (globalThis.__occeShellReminded ??= new Set());

export const OCCE_STEERING_INSTRUCTIONS = [
  "# OCCE Precision & Token-Conservation Guidelines:",
  "1. Precision Inspection: For code files (>100 lines), prefer extracting target functions/classes via `tools[\"context-optimizer\"].symbol_slice({ path, symbol })` or signatures via `code_skeleton` inside `execute`, rather than dumping full raw files.",
  "2. Indentation Safety: Do NOT write multi-line inline PowerShell string-replacement scripts (`$patch = @'...'@`). Use the built-in `edit` tool to avoid syntax and whitespace mismatch errors.",
  "3. Scoped Search: Avoid broad root-level `glob('**/*')` or unrestricted `grep`. Always specify narrow subdirectory paths to keep context high-signal.",
  "4. Token Health: To check session token health and Zen attention zones, call `tools[\"context-optimizer\"].token_ledger()`."
].join("\n");

export function injectSteeringContext(event) {
  if (!event || !Array.isArray(event.system)) return false;
  if (handledEvents.has(event)) return false;

  handledEvents.add(event);
  event.system.push({
    type: "text",
    text: OCCE_STEERING_INSTRUCTIONS
  });
  return true;
}

export function interceptShellCommand(event) {
  if (event?.tool !== "shell" && event?.tool !== "bash") return false;
  const cmd = event?.input?.command;
  if (typeof cmd !== "string") return false;

  const sessionID = event?.sessionID || "default";
  if (remindedSessions.has(sessionID)) return false;

  // Detect raw dumps of code files (e.g. Get-Content or cat without filters)
  const isRawCodeDump = /(?:Get-Content|cat|type)\s+['"]?[^'"\n]+\.(?:py|ts|tsx|js|jsx)['"]?/i.test(cmd);
  const hasFiltering = /(?:-TotalCount|-Head|-Tail|Select-String|grep|head|tail|\|)/i.test(cmd);

  if (isRawCodeDump && !hasFiltering) {
    const isWindows = process.platform === "win32";
    const reminder = isWindows
      ? 'Write-Host "[OCCE Guard: Prefer symbol_slice or code_skeleton for Python/TS files to save context]" ; '
      : 'echo "[OCCE Guard: Prefer symbol_slice or code_skeleton for Python/TS files to save context]" ; ';

    event.input = {
      ...event.input,
      command: reminder + cmd
    };
    remindedSessions.add(sessionID);
    return true;
  }

  return false;
}

function getOutputText(event) {
  if (event?.result && typeof event.result.output === "string") {
    return event.result.output;
  }
  if (typeof event?.output === "string") {
    return event.output;
  }
  if (Array.isArray(event?.result?.content) && typeof event.result.content[0]?.text === "string") {
    return event.result.content[0].text;
  }
  return null;
}

function setOutputText(event, newText) {
  if (event?.result) {
    event.result.output = newText;
    if (Array.isArray(event.result.content)) {
      event.result.content = [{ type: "text", text: newText }];
    }
  }
  if ("output" in (event || {})) {
    event.output = newText;
  }
}

export function processToolOutput(toolName, rawText) {
  if (typeof rawText !== "string" || !rawText) return rawText;

  let text = rawText.replace(ANSI_REGEX, "");

  // 1. Shell / Bash command output compression
  if (toolName === "shell" || toolName === "bash") {
    // Collapse 100% passing pytest suites
    if (text.includes("passed in") && !text.includes("FAILED") && !text.includes("FAILURES") && !text.includes("ERRORS")) {
      const passMatch = text.match(/(\d+\s+passed[^\n]*in\s+[\d\.]+s)/);
      if (passMatch) {
        return `[OCCE Guard: All pytest tests passed: ${passMatch[1]}]`;
      }
    }

    // Collapse 100% passing cargo test suites
    if (text.includes("test result: ok.") && !text.includes("FAILED")) {
      const cargoMatch = text.match(/test result:\s+ok\.\s+(\d+\s+passed)/);
      if (cargoMatch) {
        return `[OCCE Guard: Cargo tests passed: ${cargoMatch[1]}]`;
      }
    }

    // Collapse 100% passing Jest / Vitest test suites
    if ((text.includes("PASS ") || text.includes("Tests:")) && text.includes("passed") && !text.includes("FAIL ") && !text.includes("failed")) {
      const jestMatch = text.match(/Tests:\s+([^\n]+passed[^\n]*)/i);
      if (jestMatch) {
        return `[OCCE Guard: Jest/Vitest tests passed: ${jestMatch[1]}]`;
      }
    }

    // Head/tail truncate large terminal logs (>70 lines)
    const lines = text.split("\n");
    if (lines.length > 70) {
      const head = lines.slice(0, 20);
      const tail = lines.slice(-35);
      return [
        ...head,
        `\n[... OCCE Guard: ${lines.length - 55} verbose lines omitted to preserve Zen context ...]\n`,
        ...tail
      ].join("\n");
    }

    return text;
  }

  // 2. Glob tool: Compress massive file path listings (>40 paths)
  if (toolName === "glob") {
    const lines = text.split("\n").filter((l) => l.trim().length > 0);
    if (lines.length > 40) {
      const head = lines.slice(0, 25);
      const tail = lines.slice(-10);
      return [
        ...head,
        `\n[... OCCE Guard: ${lines.length - 35} file paths omitted. Narrow glob pattern or specify subdirectory ...]\n`,
        ...tail
      ].join("\n");
    }
    return text;
  }

  // 3. Grep tool: Compress large search result dumps (>35 matches)
  if (toolName === "grep") {
    const lines = text.split("\n");
    if (lines.length > 35) {
      const head = lines.slice(0, 20);
      const tail = lines.slice(-10);
      return [
        ...head,
        `\n[... OCCE Guard: ${lines.length - 30} grep matches omitted. Refine search pattern or specify path ...]\n`,
        ...tail
      ].join("\n");
    }
    return text;
  }

  // 4. Web search & Web fetch tools: Compress large HTML / raw web scrapes (>50 lines or >8000 chars)
  if (toolName === "websearch" || toolName === "webfetch") {
    const lines = text.split("\n");
    if (lines.length > 50 || text.length > 8000) {
      const head = lines.slice(0, 35);
      const tail = lines.slice(-10);
      return [
        ...head,
        `\n[... OCCE Guard: ${lines.length - 45} lines of web content omitted to preserve Zen context ...]\n`,
        ...tail
      ].join("\n");
    }
    return text;
  }

  // 5. Read tool: Large file notice
  if (toolName === "read") {
    const lines = text.split("\n");
    if (lines.length > 250) {
      return (
        `[OCCE Context Notice: Ingested large file (${lines.length} lines, ~${Math.round(lines.length * 7.5)} tokens). ` +
        `For future turns, use MCP tool 'code_skeleton' or 'symbol_slice' to conserve rate limits.]\n\n` +
        text
      );
    }
  }

  return text;
}

export default {
  id: "occe-guard",

  async setup(ctx) {
    // 1. Session steering: Inject OCCE rules into model context
    const steeringHook = async (event) => {
      injectSteeringContext(event);
    };

    if (ctx?.session?.hook) {
      await ctx.session.hook("context", steeringHook);
      await ctx.session.hook("compaction", steeringHook);
      await ctx.session.hook("generate", steeringHook);
    }

    // 2. Pre-execution interceptor: Guide shell file dumps to symbol_slice
    if (ctx?.tool?.hook) {
      await ctx.tool.hook("execute.before", async (event) => {
        interceptShellCommand(event);
      });

      // 3. Post-execution compression: Intercept shell, glob, grep, web & tool outputs
      await ctx.tool.hook("execute.after", async (event) => {
        const toolName = event.tool;
        const originalText = getOutputText(event);

        if (typeof originalText === "string") {
          const optimizedText = processToolOutput(toolName, originalText);
          if (optimizedText !== originalText) {
            setOutputText(event, optimizedText);
          }
        }
      });
    }
  }
};
