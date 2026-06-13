# Context Search Tool

Context Search Tool 是一个本地代码检索 CLI。它会在目标项目根目录下生成 `.context-search/`，把源码切块、提取词元和符号信息、写入 SQLite/FTS 与向量文件，然后用混合召回返回可读的代码上下文。

这个版本的目标很明确：先做一个可用、可扩展的检索底座。它不是简单的 `grep` 包装，也还不是完整的 ACE/Fast Context 级系统；当前重点是本地索引、混合检索、清晰输出，以及 Java/Spring 项目的第一版增强。

## 能力概览

- 本地索引：索引文件写入被检索项目的 `.context-search/`，不需要服务端。
- 混合检索：结合 SQLite FTS、离线 hash embedding、路径/符号匹配、token coverage 和插件加权。
- Java v0 增强：提取 Spring route、class/interface/enum/method/constant、enum value、SQL 注解词元。
- 上下文输出：默认 Markdown，支持 JSON，支持扩大上下文行数和小文件全文返回。
- 索引检查：查看索引文件状态、统计信息、解释某一行属于哪个 chunk。
- 配置文件：支持 include/exclude、文件大小限制、检索 top-k、上下文行数和 embedding provider。

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
- `.gitignore` 匹配的路径
- `exclude` 匹配的路径
- 超过 `max_file_bytes` 的文件
- 检测为二进制的文件

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
- MCP server

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
- MCP server 或 agent 工具接口
