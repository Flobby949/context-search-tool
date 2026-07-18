# Context Search Tool

Context Search Tool 是一个本地代码检索 CLI。它会在目标项目根目录下生成 `.context-search/`，把源码切块、提取词元和符号信息、写入 SQLite/FTS 与向量文件，然后用混合召回返回可读的代码上下文。

这个版本的目标很明确：提供一个可用、可扩展、可验证的代码检索底座。它不是简单的 `grep` 包装，也还不是完整的 ACE/Fast Context 级系统；当前已经具备本地混合索引、结构化上下文、受控探索，以及 P5 语言/框架关系图。

## 能力概览

- 本地索引：索引文件写入被检索项目的 `.context-search/`，不需要服务端。
- 多阶段检索：结合 SQLite FTS、离线 hash embedding、路径/符号匹配、token coverage、代码信号和关系扩展。
- 信号与关系模型：核心层保存语言无关的 endpoint、comment、usage、type 等信号，以及 calls、implements、uses、returns 等关系。
- 通用源码覆盖：默认扫描常见源码后缀，包括 Java、Go、Rust、Python、TypeScript/JavaScript、C/C++、C#、Kotlin、Scala、Swift、PHP、Ruby、Shell、SQL、Dart、Lua 等；没有专用插件的语言会使用通用切块和 token 检索。
- Generic query intent rerank: broad operation words such as save, update, scan, download, generate, and deploy are matched with language-neutral file roles so implementation files are favored over examples or generated artifacts unless the query explicitly asks for those artifacts.
- Java/Spring AST 图：使用随包安装的 Tree-sitter grammar 提取声明、调用、实现、类型使用和 endpoint，并以精确/唯一目标 ID 做有界关系扩展；解析失败时整文件回退。
- 框架关系：安全解析 MyBatis mapper XML，提取 Vue/React/TypeScript 静态 import、re-export 和框架锚定 route，并按六种既定语言约定建立保守的 test-to-production 关联。
- 摘要分组：查询结果会先给出 likely entry points、implementation、related types 和 possibly legacy，再展示详细代码片段。
- 上下文输出：默认 Markdown，支持 JSON，支持扩大上下文行数和小文件全文返回。
- 受控探索：显式 `explore` 模式在一次初始检索后最多执行两个确定性、planner-off 的落地探针，并返回最终 ContextPack v2 与无源码内容的 ExplorationTrace v2；普通 `query`、`context`、`trace` 仍是单轮。
- 索引检查：查看索引文件状态、统计信息、解释某一行属于哪个 chunk。
- 配置文件：支持 include/exclude、文件大小限制、检索 top-k、上下文行数和 embedding provider。
- 当前限制：P5 专用图覆盖 Java/Spring/MyBatis、Vue/React/TypeScript 静态关系和既定测试约定；Go/Gin、Rust/Axum、Spring AI `@Tool` 注册链路及增量图刷新仍需要后续阶段增强。

## 安装

需要 Python 3.11+。

开发安装：

```bash
python -m pip install -e ".[dev]"
```

安装后会得到 `cst` 命令：

```bash
cst --help
```

如果没有安装包，也可以在仓库内用模块方式运行：

```bash
PYTHONPATH=src python -m context_search_tool.cli --help
```

## 快速开始

给一个项目建立索引：

```bash
cst index /path/to/repo
```

查询一个 endpoint、枚举值或业务线索：

```bash
cst query /path/to/repo "/apply/audit/pageEs INVOLVED_BY_ME"
```

进入被检索项目后，也可以省略 repo 参数：

```bash
cd /path/to/repo
cst query "/apply/audit/pageEs INVOLVED_BY_ME"
```

扩大每个结果周围的上下文：

```bash
cst query /path/to/repo "/apply/audit/pageEs" --context-lines 20
```

输出 JSON，便于给其他工具或 agent 消费：

```bash
cst query /path/to/repo "canApply filter" --json
```

小文件可以直接返回全文：

```bash
cst query /path/to/repo "targetToken" --full-file
```

## CLI 命令

### `index`

建立或更新索引。

```bash
cst index /path/to/repo
```

第一次运行会创建：

```text
.context-search/
  config.toml
  index.sqlite
  manifest.json
  vectors.npy
  vector_ids.json
```

重复运行会跳过未变化文件，并标记已删除文件对应的 chunk。

### `query`

检索代码上下文。

```bash
cst query /path/to/repo "question or code clue"
cst query "question or code clue"
```

可选参数：

- `--json`：输出结构化 JSON。
- `--context-lines N`：覆盖默认上下文行数。
- `--full-file`：在文件小于 `max_full_file_bytes` 时返回全文。

Markdown 输出会包含：

- 文件路径和行号范围
- 总分
- 命中原因
- score parts
- 代码片段
- follow-up keywords

JSON 输出会包含同样的信息，字段包括 `results`、`score_parts`、`reasons`、`followup_keywords`。

`query` 是原始排名证据接口：它返回完整的排名结果、命中原因、分数和
follow-up keywords，适合需要自行处理原始召回的调用方。ContextPack v2
不会改变这个 CLI/MCP 请求、响应或错误合约。

### `trace`

`trace` 是显式请求的检索诊断入口。它只运行一次现有检索流水线，默认输出
Markdown，也可以输出 RetrievalTrace schema version 1 JSON；响应不包含源代码
内容：

```bash
cst trace /path/to/repo "owner registration validation"
cst trace /path/to/repo "数据看板统计图表功能" --planner --json
```

每个阶段最多预览 5 个候选，最终选择最多预览 20 项，同时保留未截断的计数。
trace 只存在于当前请求中，不会持久化或写入 MCP feedback；现有 `query` 和
ContextPack 的请求、响应及错误合约保持不变。

### `context`

`context` 只执行一次原始检索，再将同一批返回证据确定性地打包为面向
agent 的阅读集；它不会增加检索或模型调用。打包阶段不重新读取仓库，
只消费已经返回的结果、evidence anchors 和内部 span provenance。默认输出
Markdown，`--json` 输出原始 `query` 字符串和自包含的 `context_pack`：

```bash
cst context /path/to/repo "workspace page flow"
cst context /path/to/repo "workspace page flow" --json
cst context "WorkspaceServiceImpl" --context-lines 20
cst context /path/to/repo "workspace page flow" --max-items 8 --max-context-bytes 32768
```

ContextPack schema version 2 是相对 v1 的有意破坏性变更。成功 JSON envelope
的键固定为 `ok`、`repo`、`query`、`retrieval`、`context_pack`；其中
`retrieval` 只含 `result_count`、`evidence_anchor_count`、`planner_status` 和
`planner_intent`，不会复制原始 `results` 或 `evidence_anchors`。需要完整排名
数组时应调用 `query`。

`context_pack` 是 closed schema，顶层键精确为：

```text
schema_version, status, items, groups, reading_order, evidence_needs,
missing_evidence, next_queries, omissions, confidence, budget
```

它的自包含数据形态如下：

- `items` 中每项固定包含 `id`、`file_path`、`group`、`role`、
  `classification_basis`、`source_kind`、`retrieval_rank`、
  `relevance_score`、`reasons`、`matched_need_ids`、`excerpts`；源文件内容只在
  excerpt 的 `start_line`、`end_line`、`content`、`content_bytes`、`truncated`
  字段中出现一次。
- `groups` 固定包含 `entrypoints`、`implementations`、`related_types`、
  `tests`、`configs_docs`、`supporting` 六组，值是 item id；
  `reading_order` 给出确定性的阅读顺序。
- `evidence_needs` 记录具体、带 subject scope 的 required/recommended 需求及
  匹配 item；`missing_evidence`、`status`（`empty`/`partial`/`ready`）和
  `confidence` 据此如实反映当前证据，而不是把“某组非空”当作完整。
- `next_queries` 只由原查询或已落地 subject 生成；`omissions` 说明预算下未选
  证据。两者均有界且顺序稳定。

默认预算是最多 12 个 item、每项 2 个 excerpt、每 excerpt 4,096 UTF-8
bytes、每 item 8,192 content bytes、总 content 49,152 bytes，以及最多
65,536 canonical JSON pack bytes。`budget.pack_bytes` 是 compact、UTF-8、
key 顺序固定且包含自身最终整数位宽的精确字节数；`budget` 同时报告实际
item/excerpt/content、截断、遗漏和是否耗尽预算。CLI 的 `--max-items` 与
`--max-context-bytes`、MCP 的 `max_items` 与 `max_context_bytes` 使用同一解析
规则；非法值在检索前返回固定的 `invalid_context_options`。不可恢复的打包
或序列化失败统一为脱敏的 `context_failed: Context pack construction failed`；
repo、index 和 query 阶段继续使用原有错误代码。`empty` 是成功的有效空包。

### `explore`

`explore` 是显式、确定性且有界的多轮入口。它先运行一次现有检索并冻结
ContextPack 证据目标；只有目标仍缺失时，才会从已返回路径、索引符号/关系、
安全导入和固定角色后缀生成最多两个顺序执行的 follow-up。总检索调用上限为
3，follow-up 始终关闭 query planner，普通命令不会隐式触发探索：

```bash
cst explore /path/to/repo "owner registration form validation flow"
cst explore /path/to/repo "owner registration form validation flow" --json
cst explore "QRCode page route service type" --max-items 12 --max-context-bytes 65536
```

成功 JSON envelope 的键固定为 `ok`、`repo`、`query`、`retrieval`、
`context_pack`、`trace`。`context_pack` 仍是 schema version 2；`trace` 是独立的
ExplorationTrace schema version 2，记录冻结目标、round/probe 计数、增益、停止
原因和最终证据来源，但不包含源码内容。v1 不提供 round/probe/阈值配置，不做
递归探索、并发探针、模型生成探针或跨查询分数比较。

### `status`

查看索引文件是否存在。

```bash
cst status /path/to/repo
```

### `stats`

查看索引统计。

```bash
cst stats /path/to/repo
```

输出包括文件数、chunk 数、删除 chunk 数、symbol 数、lexical token 数、embedding 配置和索引磁盘占用。

### `explain`

解释某个 `file:line` 命中了哪个 chunk。

```bash
cst explain /path/to/repo src/main/java/App.java:42
```

输出包括 chunk id、chunk 类型、行号范围、符号、lexical tokens、embedding id 和 metadata。

### `clean`

删除目标项目的 `.context-search/`。

```bash
cst clean /path/to/repo
```

## MCP Server

`cst-mcp` starts a local stdio MCP server for coding agents. The server wraps the same core API as the CLI; it does not shell out to `cst`.

Available tools:

- `context_search_index(repo)` creates or updates `.context-search/`.
- `context_search_query(repo, query, context_lines, full_file, final_top_k)` returns summary, ranked results, score parts, reasons, and follow-up keywords.
- `context_search_trace(repo, query, context_lines, full_file, final_top_k)` returns bounded RetrievalTrace schema version 1 diagnostics without source content.
- `context_search_context(repo, query, context_lines, full_file, final_top_k, max_items, max_context_bytes)` returns a self-contained ContextPack schema version 2 from one raw retrieval pass while preserving the raw query string and bounded retrieval counts.
- `context_search_explore(repo, query, context_lines, full_file, final_top_k, max_items, max_context_bytes)` explicitly runs bounded controlled exploration and returns the same final ContextPack v2 plus ExplorationTrace v2.
- `context_search_stats(repo)` returns index counts and embedding configuration.
- `context_search_explain(repo, location)` explains the chunk covering a `file:line` location.

The MCP server intentionally does not expose `clean`, because deleting index state is too destructive for an agent-facing default tool.

Example local MCP config:

```json
{
  "mcpServers": {
    "context-search-tool": {
      "command": "cst-mcp",
      "args": []
    }
  }
}
```

If the package is installed in a project venv but not globally, point your agent at that venv's Python and use the module entry point:

```json
{
  "mcpServers": {
    "context-search-tool": {
      "command": "/absolute/path/to/venv/bin/python",
      "args": [
        "-m",
        "context_search_tool.mcp_server"
      ]
    }
  }
}
```

For a raw checkout without installation, set the server environment so `PYTHONPATH` includes `<repo>/src`.

For stdio MCP transport, server logs must not be written to stdout. The server returns structured tool payloads and leaves stdout for JSON-RPC. Python logging is written to `/tmp/cst-mcp.log` by default; override it with `CST_MCP_LOG_FILE=/path/to/log`.

### MCP Feedback Log

`context_search_query` appends minimal feedback events to:

```text
<repo>/.context-search/mcp_calls.jsonl
```

The log records query text, result count, top score, score parts, summary counts, follow-up keyword count, embedding fingerprint (provider, model, dimensions, and config hash), and error code. It does not record returned source snippets or full file content. When `mcp_calls.jsonl` exceeds 10 MiB, the server rotates it to `mcp_calls.<time_ns>.jsonl` before appending the next event.

`context_search_context` 在现有查询事件基础上只增加有界的 ContextPack
结构元数据，例如 schema/status、信心级别、分组/缺失类别计数和预算计数；
这部分不会增加源文件路径、excerpt 内容、need subject 或组合出的下一步
查询文本。基础反馈事件仍按上文记录调用的原始 query，因此反馈文件应继续
按包含查询文本的本地日志管理。

`context_search_trace` 不会创建或修改反馈日志；trace 数据始终是请求本地数据。

`context_search_explore` 只追加聚合计数：trace schema/mode/outcome、停止原因、
目标/round/probe/call/最终证据计数和限额。它不会把生成的 probe/query、goal
ID、seed/final path、源码内容、source-count 明细或异常文本写入 feedback。

Use this log to decide embedding work:

- If endpoint, class, enum, and field searches are strong but Chinese business-description searches miss, test a real embedding provider.
- If the right files appear but ranking is weak, tune reranking before changing embedding.
- If implementation chains are missing, improve Java/MyBatis relation signals before changing embedding.
- Keep `hash-v1` as the default until MCP call evidence shows it is the limiting factor.

## 配置

配置文件位于被索引项目的：

```text
.context-search/config.toml
```

默认配置形态：

```toml
[index]
include = []
exclude = []
max_file_bytes = 500000
max_full_file_bytes = 200000

[retrieval]
semantic_top_k = 80
lexical_top_k = 80
final_top_k = 12
context_before_lines = 8
context_after_lines = 12

[context]
max_items = 12
max_excerpts_per_item = 2
max_excerpt_bytes = 4096
max_item_content_bytes = 8192
max_total_content_bytes = 49152
max_pack_bytes = 65536

[embedding]
provider = "hash"
model = "hash-v1"
dimensions = 384
```

### Include / Exclude

`include` 为空时，会扫描所有支持的源码类型。设置后只扫描匹配的文件：

```toml
[index]
include = ["src/**/*.java"]
exclude = ["target/", "build/"]
```

扫描会自动跳过：

- `.git/`
- `.context-search/`
- 常见依赖和构建目录，如 `node_modules/`、`vendor/`、`.venv/`、`dist/`、`build/`、`target/`
- `.gitignore` 匹配的路径
- `exclude` 匹配的路径
- 超过 `max_file_bytes` 的文件
- 检测为二进制的文件

### Generic Language Baseline

常见源码后缀会被通用索引覆盖，即使没有对应语言或框架插件，也会按 generic chunk 和 token 进入检索。`cst stats` 可能显示 `Symbols: 0`；这只表示没有插件产出符号，不代表源码没有索引。代码型查询仍会使用路径词、标识符、注释、字符串和邻近源码文本。

为了让源码结果保持优先，代码导向查询可能会降低 generated schema、已索引 lockfile、template、普通 docs 和 config 的排序权重。`README`、`RISKS`、`pom` 这类文件仍可能作为 evidence anchors 出现，用来解释命中背景，但不一定作为 primary results 排在前面。

框架插件是可选增强层：例如 Java/Spring 插件会补充 endpoint、comment、usage 和 relation 信号；没有插件时，CST 仍保留通用源码检索基线。如果 `cst stats` 对正常源码仓库只显示 README/config 文件，先检查源码后缀是否在 scanner language map 中，并补 scanner 回归测试，再调整排序。

CST also treats explicit code intent as a generic ranking signal. Queries that name identifiers such as `UploadHandler`, `useAuthStore`, `apply_dev`, filenames such as `nav.go`, or broad path roles such as `handler`, `service`, `store`, `composable`, `command`, and `engine` receive explainable rerank support. These are language-neutral baseline signals, not framework plugins.

### P5 语言/框架图与数据边界

索引升级到 signal schema v5 后，CST 会执行一次完整重建；从 v4 迁移时不能复用旧 chunk/vector/graph 快照。Tree-sitter parser、图解析器和 XML 校验都在本机运行，索引过程不会下载 grammar、执行被索引仓库的代码或调用其构建工具。图处于 stale 状态时，signal/relation evidence 会关闭，但 lexical、path、hash embedding 等基础召回仍可用。

“本地图”不等于“所有数据永不离机”。默认 `hash-v1` 完全离线；如果配置远程 embedding provider，源码 chunk 会发送给该 provider，v5 全量迁移也可能重发全部 chunk。`query`/`explore` 还会发送正常 query/probe 文本，其中可能包含图派生的名称或路径；AST、signal、relation 和 explain 对象不会作为单独远程 payload 发送。

### Monorepo Root Indexing

CST 可以直接索引 monorepo 根目录，并使用 `package.json`、`go.mod`、`pom.xml` 等通用 project markers 识别子项目边界。查询时匹配到的 project scope 会作为 soft rerank signal 使用，因此 frontend、collector 这类查询即使和 backend 共享业务词，也可以优先浮出自己子项目里的文件。

如果已经知道目标子项目，直接索引子项目仍然是有效 workaround：

```bash
cst index /path/to/repo/frontend
cst query /path/to/repo/frontend "useAuthStore login register fetchCurrentUser"
```

### Embedding Provider

默认 provider 是 `hash`：

```toml
[embedding]
provider = "hash"
model = "hash-v1"
dimensions = 384
```

它是确定性、离线、零依赖服务的 embedding。它适合开发、测试，以及 endpoint、类名、字段名、枚举值这类代码 token 密集的搜索。

也可以配置 OpenAI-compatible embedding 服务：

```toml
[embedding]
provider = "openai-compatible"
model = "text-embedding-3-small"
dimensions = 1536
base_url = "http://127.0.0.1:8000/v1"
api_key_env = "EMBEDDING_API_KEY"
```

服务需要暴露 `/v1/embeddings` 风格接口。修改 embedding provider、model、dimensions 或 base_url 后，需要重新索引；旧索引会通过 manifest 兼容性检查阻止误用。

### BGE Provider (Local via Ollama)

For local semantic embeddings without external API calls:

```toml
[embedding]
provider = "bge"
model = "bge-m3"
dimensions = 1024
```

BGE-M3 runs locally via Ollama service. Requires:
- Ollama installed and running
- BGE-M3 model: `ollama pull bge-m3`

Advantages:
- No API costs
- Works offline
- Strong multilingual support (English + Chinese)
- 1024-dimensional embeddings
- Fast inference via Ollama

Disadvantages:
- Requires Ollama service running
- HTTP API overhead (minimal)
- ~1.2GB model storage

Best for: Semantic searches on business descriptions, cross-language queries, or when API access is unavailable.

## 检索流程

当前检索 pipeline 大致是：

1. Scanner 读取项目文件，应用 `.gitignore`、include/exclude、大小限制和二进制检测。
2. Chunker 按行切块，并把插件提取到的符号映射到相关 chunk。
3. Java plugin 提取 Java/Spring 的 route、符号、enum value 和 SQL 注解词元。
4. SQLite store 保存 source file、chunk、symbol、lexical token，并建立 FTS 索引。
5. Vector store 保存 chunk embedding 到 `vectors.npy`，用 `vector_ids.json` 对齐 chunk id。
6. Query 阶段合并 semantic、lexical、path/symbol 召回候选。
7. Rerank 阶段计算 token coverage、Java/plugin boost、route boost 和 generated/test penalty。
8. Formatter 输出 Markdown 或 JSON。

结果里的 `reasons` 用来解释为什么命中，例如：

- `semantic match`
- `lexical match`
- `path/symbol match`
- `token coverage`
- `route token match`
- `java plugin boost`

## Java 支持范围

当前 Java plugin 是轻量级文本解析，不是 AST 解析器。它支持：

- `package` 和 `import` 词元
- `class`、`interface`、`enum`
- 方法、常量、enum value
- Spring mapping 注解：
  - `@RequestMapping`
  - `@GetMapping`
  - `@PostMapping`
  - `@PutMapping`
  - `@DeleteMapping`
  - `@PatchMapping`
- class-level route 和 method-level route 拼接
- SQL 注解词元：
  - `@Select`
  - `@Insert`
  - `@Update`
  - `@Delete`
- 注释剥离，避免注释里的 dead route / dead symbol 污染索引

它适合这类问题：

```bash
cst query /repo "/apply/audit/pageEs INVOLVED_BY_ME"
cst query /repo "canApply filter"
cst query /repo "app_org_region_code TOTAL_OVERVIEW"
```

当前还不支持：

- tree-sitter 或 JDT AST
- MyBatis XML 关系解析
- Lombok 生成方法推断
- 调用图 / 引用图 rerank
- 类型解析或跨文件符号绑定
- LLM reranker
- Fast Context 风格的 agentic multi-stage retrieval
- remote MCP deployment or hosted multi-user service

## 输出示例

Markdown 查询结果类似：

```markdown
# Context Search Results

Query: /apply/audit/pageEs INVOLVED_BY_ME
Expanded tokens: apply, audit, page, es, involved, by, me

## Results

### 1. src/main/java/com/example/audit/ApplyAuditController.java:1-14
Score: 0.7499

Reasons:
- lexical match
- path/symbol match
- token coverage
- route token match

Score parts:
- lexical: 0.99
- path_symbol: 13.0
- plugin_boost: 0.15
- route_boost: 0.12
- token_coverage: 1.0
```

JSON 查询结果适合后续自动处理：

```bash
cst query /path/to/repo "/apply/audit/pageEs" --json
```

## 故障排查

### 查询时报 missing index

先运行：

```bash
cst index /path/to/repo
```

### 修改 embedding 配置后查询报 incompatible

embedding 配置会写入 manifest。修改 provider、model、dimensions 或 base_url 后，旧索引不能继续混用。

清理并重建：

```bash
cst clean /path/to/repo
cst index /path/to/repo
```

### openai-compatible 缺少 base_url

配置中必须写：

```toml
[embedding]
provider = "openai-compatible"
base_url = "http://127.0.0.1:8000/v1"
```

### 查询结果太窄

增加上下文：

```bash
cst query /path/to/repo "query" --context-lines 30
```

或者对小文件使用：

```bash
cst query /path/to/repo "query" --full-file
```

## 开发

安装开发依赖：

```bash
python -m pip install -e ".[dev]"
```

运行测试：

```bash
pytest -v -m "not slow"
```

已启动本机 Ollama/BGE 服务时，可去掉 marker 过滤运行包括集成项在内的完整套件。

检索质量的标准 CI、真实仓库 smoke、planner、BGE A/B、报告比较和 MCP
反馈流程见 [Retrieval Quality Workflow](docs/retrieval-quality.md)。快速本地门禁：

```bash
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile ci --output .quality/ci.json --markdown .quality/ci.md
```

真实项目 smoke：

```bash
CST_SMOKE_REPOS_DIR=/absolute/path/to/repos \
cst quality run tests/fixtures/retrieval_quality/queries.json \
  --profile smoke --output .quality/smoke.json --markdown .quality/smoke.md
```

项目模块：

```text
src/context_search_tool/
  cli.py            CLI 入口
  config.py         配置读写
  paths.py          repo 和 .context-search 路径
  scanner.py        文件扫描和 ignore 处理
  tokenizer.py      代码词元切分
  chunker.py        源码切块
  java_plugin.py    Java/Spring 轻量提取
  syntax_parsers.py 本地 Tree-sitter parser 构造边界
  java_ast.py       Java AST facts
  java_graph.py     Java/Spring v5 图生产者
  frontend_graph.py Vue/React/TypeScript route/import 图
  mybatis_xml.py    fail-closed MyBatis XML 图
  graph_resolution.py 结构化 selector 解析
  sqlite_store.py   SQLite metadata 与 FTS
  embeddings.py     hash/openai-compatible embedding provider
  vector_store.py   NumPy 向量持久化和搜索
  manifest.py       索引兼容性 manifest
  retrieval.py      混合召回和 rerank
  retrieval_trace/  RetrievalTrace 契约、采集和序列化
  formatters.py     Markdown/JSON 输出
```

测试覆盖了 scanner、chunker、Java plugin、SQLite store、embedding/vector store、manifest/indexer、retrieval、formatter、CLI，以及一个 Java mini fixture acceptance case。

## 当前定位

当前版本已经可以作为本地代码检索底座使用，尤其适合从 Java/Spring endpoint、service/interface/mapper/XML/DTO/test 链路，或 Vue/React route/view/service/type 链路出发找相关上下文。

下一阶段是 P6：索引 freshness、增量刷新、大仓性能和可观测性。更强 embedding/provider 与额外语言插件仍可继续评估，但不会替代本地精确召回。
- cross-encoder 或 LLM rerank
- remote MCP deployment or hosted multi-user service
