# Context Search Tool

Context Search Tool 是一个本地代码检索 CLI。它会在目标项目根目录下生成 `.context-search/`，把源码切块、提取词元和符号信息、写入 SQLite/FTS 与向量文件，然后用混合召回返回可读的代码上下文。

这个版本的目标很明确：先做一个可用、可扩展的检索底座。它不是简单的 `grep` 包装，也还不是完整的 ACE/Fast Context 级系统；当前重点是本地索引、混合检索、清晰输出，以及 Java/Spring 项目的第一版增强。

## 能力概览

- 本地索引：索引文件写入被检索项目的 `.context-search/`，不需要服务端。
- 多阶段检索：结合 SQLite FTS、离线 hash embedding、路径/符号匹配、token coverage、代码信号和关系扩展。
- 信号与关系模型：核心层保存语言无关的 endpoint、comment、usage、type 等信号，以及 calls、implements、uses、returns 等关系。
- 通用源码覆盖：默认扫描常见源码后缀，包括 Java、Go、Rust、Python、TypeScript/JavaScript、C/C++、C#、Kotlin、Scala、Swift、PHP、Ruby、Shell、SQL、Dart、Lua 等；没有专用插件的语言会使用通用切块和 token 检索。
- Java 增强：Java/Spring 是第一版信号生产者，可提取 Spring endpoint、JavaDoc/comment、方法调用 usage、短链 relation、class/interface/enum/method/constant、enum value 和 SQL 注解词元。
- 摘要分组：查询结果会先给出 likely entry points、implementation、related types 和 possibly legacy，再展示详细代码片段。
- 上下文输出：默认 Markdown，支持 JSON，支持扩大上下文行数和小文件全文返回。
- 索引检查：查看索引文件状态、统计信息、解释某一行属于哪个 chunk。
- 配置文件：支持 include/exclude、文件大小限制、检索 top-k、上下文行数和 embedding provider。
- 当前限制：通用语言覆盖只保证源码能索引和按文本/token 检索；框架语义如 Go/Gin 路由、Rust/Axum 路由、Spring AI `@Tool` 注册链路需要后续语言或框架插件增强。

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
pytest -v
```

真实项目通用基线 smoke（需要 `CST_SMOKE_REPOS_DIR` 指向已准备好的真实项目目录）：

```bash
CST_SMOKE_REPOS_DIR=/Users/flobby/vibe_coding /opt/homebrew/Caskroom/miniforge/base/bin/python -m pytest tests/test_generic_baseline_quality.py -m "slow and integration" -q
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
  sqlite_store.py   SQLite metadata 与 FTS
  embeddings.py     hash/openai-compatible embedding provider
  vector_store.py   NumPy 向量持久化和搜索
  manifest.py       索引兼容性 manifest
  retrieval.py      混合召回和 rerank
  formatters.py     Markdown/JSON 输出
```

测试覆盖了 scanner、chunker、Java plugin、SQLite store、embedding/vector store、manifest/indexer、retrieval、formatter、CLI，以及一个 Java mini fixture acceptance case。

## 当前定位

第一版已经可以作为本地代码检索底座使用，尤其适合 Java/Spring 项目里从 endpoint、枚举值、DTO 字段、mapper 或业务关键词出发找相关上下文。

下一阶段更值得投入的方向是：

- Java AST 级解析
- MyBatis XML 和 mapper 方法关联
- 符号引用图 / 调用图
- 更强 embedding provider
- cross-encoder 或 LLM rerank
- remote MCP deployment or hosted multi-user service
