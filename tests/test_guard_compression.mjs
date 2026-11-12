import { processToolOutput } from "../plugins/occe-guard.js";
import assert from "node:assert";

console.log("=== TESTING OCCE-GUARD.JS TOOL OUTPUT COMPRESSION ===");

// 1. Git status clean
const cleanGit = "## main...origin/main\n";
const resGit = processToolOutput("shell", cleanGit);
assert.strictEqual(resGit, "[OCCE Guard: Git working tree clean on main]");
console.log("[PASS] Clean git status compressed");

// 2. Git status dirty (MUST NOT BE COMPRESSED - fidelity check!)
const dirtyGit = "## main...origin/main\n M backend/app/main.py\n?? new_file.txt\n";
const resDirtyGit = processToolOutput("shell", dirtyGit);
assert.strictEqual(resDirtyGit, dirtyGit);
console.log("[PASS] Dirty git status preserved 100% without modification");

// 3. Passing pytest
const passPytest = "================ 42 passed in 1.45s ================\n";
const resPytest = processToolOutput("shell", passPytest);
assert.ok(resPytest.includes("[OCCE Guard: All pytest tests passed: 42 passed in 1.45s]"));
console.log("[PASS] Passing pytest compressed");

// 4. Failing pytest (MUST NOT BE COMPRESSED - fidelity check!)
const failPytest = "================ FAILURES ================\nassert 401 == 200\n1 failed, 41 passed in 1.50s\n";
const resFailPytest = processToolOutput("shell", failPytest);
assert.strictEqual(resFailPytest, failPytest);
console.log("[PASS] Failing pytest preserved 100% with exact failure details");

// 5. Ruff check passing
const passRuff = "All checks passed!\n";
const resRuff = processToolOutput("shell", passRuff);
assert.ok(resRuff.includes("[OCCE Guard: All checks passed!]"));
console.log("[PASS] Passing Ruff checks compressed");

// 6. Ruff check failing (MUST NOT BE COMPRESSED)
const failRuff = "src/main.py:10:1: F401 `os` imported but unused\nFound 1 error.\n";
const resFailRuff = processToolOutput("shell", failRuff);
assert.strictEqual(resFailRuff, failRuff);
console.log("[PASS] Failing Ruff checks preserved 100%");

console.log("\n>>> ALL OCCE-GUARD COMPRESSION & FIDELITY TESTS PASSED! <<<");
