/**
 * OCCE v3 Typed Sandbox API (`occe.d.ts`)
 * Exposed inside the Code-Mode V8 isolate as global `occe`.
 * Intermediate outputs stay in isolate memory; only your `return` value reaches the LLM.
 */
declare namespace occe {
  export interface SkeletonOptions {
    path: string;
    depth?: number;
  }

  export interface SymbolSliceOptions {
    path: string;
    symbol: string;
  }

  export interface FileSliceOptions {
    path: string;
    start_line?: number;
    end_line?: number;
    max_lines?: number;
  }

  export interface SmartExecOptions {
    command: string;
    max_lines?: number;
  }

  export interface TestCompressOptions {
    command: string;
  }

  export interface DiffCompactOptions {
    filepath?: string;
    staged?: boolean;
    exclude_generated?: boolean;
  }

  export interface ToolResult {
    text: string;
    isError: boolean;
  }

  export interface HandoffSummary {
    branch: string;
    headSha: string;
    status: string;
    recentCommits: string[];
    compactDiff: string;
    ledger: Record<string, unknown>;
  }

  function codeSkeleton(opts: SkeletonOptions): Promise<ToolResult>;
  function symbolSlice(opts: SymbolSliceOptions): Promise<ToolResult>;
  function fileSlice(opts: FileSliceOptions): Promise<ToolResult>;
  function smartExec(opts: SmartExecOptions): Promise<ToolResult>;
  function testCompress(opts: TestCompressOptions): Promise<ToolResult>;
  function diffCompact(opts?: DiffCompactOptions): Promise<ToolResult>;
  function tokenLedger(): Promise<ToolResult>;
  function sessionHandoff(): Promise<HandoffSummary>;
}
