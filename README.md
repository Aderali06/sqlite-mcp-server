# sqlite-mcp-server

An open-source [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server connecting LLM assistants (such as **Claude Desktop** and **Cursor**) to **local SQLite databases** with strict read-only security, context overflow protection, and structured AI error handling.

[![CI](https://github.com/Aderali06/sqlite-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/Aderali06/sqlite-mcp-server/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## 🌟 Key Features

- **Automated Schema Discovery**: Automatically inspect table lists, object types (tables/views), row count estimates, columns, primary keys, foreign keys, and complete DDL definitions.
- **Strict Read-Only Query Security**:
  - **Parser-Level Validation**: Rejects all mutation statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`, `VACUUM`, `REINDEX`, etc.).
  - **Statement Chaining Prevention**: Blocks execution of multiple chained statements separated by `;`.
  - **Restricted PRAGMAs**: Prohibits dangerous PRAGMAs (`writable_schema`, permissions, and configuration mutation).
  - **Engine-Level Enforcement**: SQLite connections are opened using read-only URI mode (`file:path?mode=ro`) with `PRAGMA query_only = ON;`.
- **Context Overflow Protection (`max_rows`)**: Safely truncates large query results with an informative warning advising AI models to use `LIMIT` and `OFFSET` clauses.
- **Structured Error Handling for AI**: Returns standardized JSON error envelopes (`error_type`, `message`, `query`, and `suggestion`) to allow AI models to self-correct queries without hallucinations.
- **Full MCP Capabilities**: Exposes **Tools**, direct **Resources** (`sqlite://schema`, `sqlite://tables`), and guided **Prompts** (`schema_analysis`, `safe_query_assistant`).
- **Flexible Configuration**: Set the database path via CLI argument (`--db-path`), environment variable (`SQLITE_DB_PATH`), or dynamically per tool invocation (`db_path`).

---

## 🛠️ MCP Tools

| Tool Name | Description | Key Arguments |
| :--- | :--- | :--- |
| `list_tables` | Lists all tables and views in the database with estimated row counts. | `db_path` *(optional)* |
| `describe_table` | Retrieves column definitions, data types, nullability, default values, primary keys, foreign keys, and indexes for a specific table. | `table_name` *(required)*, `db_path` *(optional)* |
| `get_database_schema` | Returns the complete DDL schema definition for all tables, views, and indexes. | `db_path` *(optional)* |
| `read_query` | Safely executes a read-only `SELECT` or `EXPLAIN` query and returns structured row records. | `query` *(required)*, `params` *(optional)*, `max_rows` *(optional, default: 1000)*, `db_path` *(optional)* |

---

## 📦 MCP Resources & Prompts

### MCP Resources (Direct Context Access)
Clients that support MCP Resources can inspect the database context directly without invoking a tool:
- `sqlite://schema`: Returns the full formatted SQL DDL schema of the database.
- `sqlite://tables`: Returns a concise list of all tables, views, and their respective row counts.

### MCP Prompts (Interactive Assistant Guides)
- `schema_analysis`: Prompts the AI model to inspect database structure, relationships, normalization, and optimization opportunities.
- `safe_query_assistant(user_goal)`: Guides the AI model in formulating an optimized, safe `SELECT` query tailored to the user's objective.

---

## 📋 Structured Error Format

When a syntax or validation error occurs, the server responds with a structured JSON object designed for LLM consumption:

```json
{
  "success": false,
  "error_type": "DisallowedQueryError",
  "message": "Forbidden modification keyword 'DROP' detected. Only read operations are allowed.",
  "query": "DROP TABLE employees;",
  "suggestion": "Remove any data modification or schema alteration commands. Only SELECT queries are permitted."
}
```

Supported error categories:
- `DisallowedQueryError`: Query attempts data modification or invokes forbidden SQL operations.
- `SyntaxError`: SQLite syntax error.
- `TableNotFoundError`: Table was not found (includes advice to run `list_tables`).
- `ColumnNotFoundError`: Column was not found (includes advice to run `describe_table`).
- `DatabaseNotFoundError`: Database file does not exist at the specified path.
- `DatabaseConfigError`: No database path was provided or configured.
- `ValidationError`: Invalid input parameter (e.g. empty table name or `max_rows < 1`).

---

## 🚀 Installation & Getting Started

### Option 1: Run with `uvx` (Recommended)
If you have `uv` installed, run the server instantly without cloning:
```bash
uvx sqlite-mcp-server --db-path "/path/to/database.db"
```

### Option 2: Install from Source
```bash
# 1. Clone repository
git clone https://github.com/Aderali06/sqlite-mcp-server.git
cd sqlite-mcp-server

# 2. Create virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install package and development dependencies
pip install -e ".[dev]"
```

---

## ⚙️ Claude Desktop Configuration

Add the server to your `claude_desktop_config.json`:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Configuration Example:

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uvx",
      "args": [
        "sqlite-mcp-server",
        "--db-path",
        "C:/Users/A2/Documents/database.db"
      ]
    }
  }
}
```

*Or using local Python:*
```json
{
  "mcpServers": {
    "sqlite": {
      "command": "python",
      "args": [
        "-m",
        "src.server",
        "--db-path",
        "C:/Users/A2/Documents/database.db"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

---

## 💻 Cursor Integration

### Method 1: Via Cursor Settings UI
1. Open **Cursor Settings** (`Ctrl + Shift + J` on Windows/Linux or `Cmd + ,` on macOS).
2. Navigate to **Features** > **MCP Servers**.
3. Click **+ Add New MCP Server**.
4. Fill in:
   - **Name**: `sqlite-mcp-server`
   - **Type**: `command`
   - **Command**: `python -m src.server --db-path "C:/path/to/database.sqlite"`

### Method 2: Project-Level Configuration (`.cursor/mcp.json`)
Create `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "python",
      "args": [
        "-m",
        "src.server",
        "--db-path",
        "${workspaceFolder}/data/app.db"
      ]
    }
  }
}
```

---

## 🧪 Testing

Run the automated test suite with `pytest`:

```bash
# Run all tests
pytest

# Run tests with test coverage reporting
pytest --cov=src --cov-report=term-missing
```

---

## 📂 Project Structure

```
sqlite-mcp-server/
├── .github/
│   └── workflows/
│       ├── ci.yml              # Multi-OS CI testing (Linux & Windows)
│       └── publish.yml         # Automated PyPI release workflow
├── src/
│   ├── __init__.py             # Package version & metadata
│   └── server.py               # FastMCP server, tools, resources, prompts & SQL validation
├── tests/
│   └── test_server.py          # 29 unit & integration pytest tests
├── .gitignore                  # Git ignore rules
├── LICENSE                     # Official MIT License
├── pyproject.toml              # Build system, CLI entrypoint, & package metadata
├── README.md                   # Project documentation & configuration guide
└── requirements.txt            # Python dependencies
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
