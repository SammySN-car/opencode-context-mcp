/**
 * OCCE OpenCode Companion Plugin Hook (`occe-guard.ts`)
 *
 * Automatically intercepts built-in OpenCode tools (bash, read) to apply
 * ANSI stripping, test collapsing, and context truncation transparently
 * without requiring the model to remember to call MCP tools.
 *
 * Install in your project at: `.opencode/plugins/occe-guard.ts`
 * or globally in `~/.config/opencode/plugins/`
 */

import { Plugin } from "@opencode-ai/plugin";

export default function occeGuardPlugin(): Plugin {
  const ANSI_REGEX = /(?:\x1B[@-Z\\-_]|[\x80-\x9A\x9C-\x9F]|(?:\x1B\[|\x9B)[0-?]*[ -/]*[@-~])/g;

  return {
    name: "occe-guard",
    setup(ctx) {
      // 1. Intercept built-in bash output after execution
      ctx.tool.hook("execute.after", async (event) => {
        if (event.tool === "bash" && typeof event.output === "string") {
          let text = event.output.replace(ANSI_REGEX, "");

          // Collapse 100% passing test suites into 1-line summary
          if (text.includes("passed in") && !text.includes("FAILED") && !text.includes("FAILURES")) {
            const passMatch = text.match(/(\d+\s+passed[^\n]*in\s+[\d\.]+s)/);
            if (passMatch) {
              event.output = `[OCCE Guard: All tests passed: ${passMatch[1]}]`;
              return;
            }
          }

          // Cargo test collapse
          if (text.includes("test result: ok.") && !text.includes("FAILED")) {
            const cargoMatch = text.match(/test result:\s+ok\.\s+(\d+\s+passed)/);
            if (cargoMatch) {
              event.output = `[OCCE Guard: Cargo tests passed: ${cargoMatch[1]}]`;
              return;
            }
          }

          // Saliency-preserving head/tail truncation if massive
          const lines = text.split("\n");
          if (lines.length > 70) {
            const head = lines.slice(0, 20);
            const tail = lines.slice(-35);
            event.output = [
              ...head,
              `\n[... OCCE Guard: ${lines.length - 55} verbose lines omitted to preserve context ...]\n`,
              ...tail
            ].join("\n");
          } else {
            event.output = text;
          }
        }

        // 2. Intercept built-in read output to warn on huge files
        if (event.tool === "read" && typeof event.output === "string") {
          const lines = event.output.split("\n");
          if (lines.length > 250) {
            event.output = (
              `[OCCE Context Notice: Ingested large file (${lines.length} lines, ~${Math.round(lines.length * 7.5)} tokens). ` +
              `For future turns, consider using MCP 'code_skeleton' or 'symbol_slice' to conserve Zen rate limits.]\n\n` +
              event.output
            );
          }
        }
      });
    }
  };
}
