"""SQLite MCP Server.

Provides a Model Context Protocol (MCP) server for inspecting and querying
local SQLite databases with strict read-only guarantees and structured errors.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

try:
    # MCP SDK 2.x (FastMCP renamed to MCPServer)
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    try:
        # MCP SDK 1.x
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except ImportError:  # pragma: no cover
        # Graceful fallback for minimal environments running unit tests before installing MCP
        class FastMCP:  # type: ignore
            """Minimal fallback stub for FastMCP when mcp package is missing."""
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def tool(self, *args: Any, **kwargs: Any) -> Any:
                def decorator(func: Any) -> Any:
                    return func
                return decorator

            def resource(self, *args: Any, **kwargs: Any) -> Any:
                def decorator(func: Any) -> Any:
                    return func
                return decorator

            def prompt(self, *args: Any, **kwargs: Any) -> Any:
                def decorator(func: Any) -> Any:
                    return func
                return decorator

            def run(self, *args: Any, **kwargs: Any) -> None:
                raise RuntimeError("The 'mcp' package is required to run server. Run: pip install mcp")

# Global configured database path, fallback to environment variable
DEFAULT_DB_PATH: str | None = os.environ.get("SQLITE_DB_PATH")

# Initialize FastMCP Server
mcp = FastMCP(
    "sqlite-mcp-server",
    instructions=(
        "You have access to a local SQLite database through this MCP server. "
        "Use list_tables to see available tables, describe_table to inspect table structure, "
        "get_database_schema to inspect the entire database DDL, and read_query to run safe SELECT queries. "
        "All mutation queries (INSERT, UPDATE, DELETE, DROP, etc.) are strictly prohibited."
    ),
)

# Regex patterns for SQL query validation
DISALLOWED_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "REPLACE",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "REINDEX",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
}

DISALLOWED_PRAGMAS = {
    "WRITABLE_SCHEMA",
    "QUERY_ONLY",
    "AUTO_VACUUM",
    "INCREMENTAL_VACUUM",
    "FOREIGN_KEYS",
    "JOURNAL_MODE",
    "SYNCHRONOUS",
    "LOCKING_MODE",
}


def strip_sql_comments(sql: str) -> str:
    """Remove single-line and multi-line SQL comments."""
    # Remove single-line comments (-- comment)
    sql_no_single = re.sub(r"--[^\n]*", "", sql)
    # Remove multi-line comments (/* comment */)
    sql_no_multi = re.sub(r"/\*[\s\S]*?\*/", "", sql_no_single)
    return sql_no_multi.strip()


def validate_read_only_query(query: str) -> tuple[bool, str | None, str | None]:
    """Validate that an SQL query is strictly read-only and safe.

    Returns:
        (is_valid, error_message, suggestion)
    """
    if not query or not query.strip():
        return False, "Query cannot be empty.", "Provide a valid SELECT query."

    cleaned_sql = strip_sql_comments(query).strip()
    if not cleaned_sql:
        return False, "Query contains only comments or whitespace.", "Provide a valid SELECT query."

    # Check for multiple statements (semicolon not enclosed in string literals)
    # Strip any trailing semicolon first
    sql_body = cleaned_sql.rstrip(";").strip()

    # Check if there are internal semicolons outside single/double quotes
    in_single = False
    in_double = False
    for char in sql_body:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ";" and not in_single and not in_double:
            return (
                False,
                "Multiple SQL statements are not permitted in a single query.",
                "Execute only one SELECT query at a time without chaining statements with ';'.",
            )

    # Extract all uppercase words/tokens to check for disallowed commands
    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", cleaned_sql)
    if not tokens:
        return False, "No valid SQL tokens found.", "Provide a valid SELECT query."

    first_keyword = tokens[0].upper()

    # Allowed leading keywords for read queries
    allowed_first_keywords = {"SELECT", "WITH", "EXPLAIN", "PRAGMA"}
    if first_keyword not in allowed_first_keywords:
        return (
            False,
            f"Query statement type '{first_keyword}' is not allowed. Only read-only queries are permitted.",
            "Only SELECT, WITH (CTE), EXPLAIN, and read-only PRAGMA statements are supported.",
        )

    # If first keyword is PRAGMA, ensure it doesn't set values or call dangerous pragmas
    if first_keyword == "PRAGMA":
        # PRAGMAs that attempt to write have '=' or '(' with values
        if "=" in cleaned_sql:
            return (
                False,
                "Modifying database PRAGMA settings is strictly forbidden.",
                "Use read-only PRAGMAs such as 'PRAGMA table_info(table_name)'.",
            )
        if len(tokens) > 1 and tokens[1].upper() in DISALLOWED_PRAGMAS:
            return (
                False,
                f"PRAGMA '{tokens[1]}' is restricted for security reasons.",
                "Use standard inspection tools or read-only PRAGMAs such as 'PRAGMA table_info'.",
            )

    # Scan all tokens for forbidden mutation keywords
    upper_tokens = [t.upper() for t in tokens]
    for kw in DISALLOWED_KEYWORDS:
        if kw in upper_tokens:
            return (
                False,
                f"Forbidden modification keyword '{kw}' detected. Only read operations are allowed.",
                "Remove any data modification or schema alteration commands. Only SELECT queries are permitted.",
            )

    return True, None, None


def resolve_database_path(db_path: str | None = None) -> tuple[Path | None, dict[str, Any] | None]:
    """Resolve database path from argument, default global variable, or environment.

    Returns:
        (resolved_path, error_dict)
    """
    target = db_path or DEFAULT_DB_PATH or os.environ.get("SQLITE_DB_PATH")

    if not target:
        return None, {
            "success": False,
            "error_type": "DatabaseConfigError",
            "message": "No database path provided.",
            "suggestion": (
                "Please provide 'db_path' in tool arguments or set the "
                "'SQLITE_DB_PATH' environment variable / start server with --db-path."
            ),
        }

    path = Path(target).expanduser().resolve()
    if not path.is_file():
        return None, {
            "success": False,
            "error_type": "DatabaseNotFoundError",
            "message": f"Database file does not exist: {path}",
            "suggestion": "Verify that the path is correct and points to an existing SQLite database file.",
        }

    return path, None


def get_connection(db_path: str | None = None) -> tuple[sqlite3.Connection | None, dict[str, Any] | None]:
    """Create a safe, read-only SQLite database connection."""
    path, err = resolve_database_path(db_path)
    if err or path is None:
        return None, err

    try:
        # Use SQLite URI mode to open in read-only mode (mode=ro)
        # On Windows, Path.as_uri() handles drive letters correctly
        db_uri = f"{path.as_uri()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Extra safety enforcement at the engine level
        conn.execute("PRAGMA query_only = ON;")
        return conn, None
    except sqlite3.Error as ex:
        return None, {
            "success": False,
            "error_type": "ConnectionError",
            "message": f"Failed to connect to database: {str(ex)}",
            "suggestion": "Ensure the file is a valid, uncorrupted SQLite database with read permissions.",
        }


# ---------------------------------------------------------------------------
# Core Database Inspection & Query Logic (Pure functions for easy testing)
# ---------------------------------------------------------------------------

def execute_list_tables(db_path: str | None = None) -> dict[str, Any]:
    """Retrieve all tables and views from the SQLite database."""
    conn, err = get_connection(db_path)
    if err:
        return err

    assert conn is not None
    try:
        cursor = conn.cursor()
        query = (
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type, name;"
        )
        cursor.execute(query)
        records = cursor.fetchall()

        tables = []
        for row in records:
            name = row["name"]
            table_type = row["type"]

            # Count rows for regular tables safely
            row_count: int | None = None
            if table_type == "table":
                try:
                    escaped_name = name.replace('"', '""')
                    count_cur = conn.cursor()
                    count_cur.execute(f'SELECT COUNT(*) FROM "{escaped_name}"')
                    count_row = count_cur.fetchone()
                    if count_row:
                        row_count = count_row[0]
                except Exception:
                    row_count = None

            tables.append({
                "name": name,
                "type": table_type,
                "row_count": row_count,
            })

        return {
            "success": True,
            "database": str(resolve_database_path(db_path)[0]),
            "table_count": len(tables),
            "tables": tables,
        }
    except sqlite3.Error as ex:
        return {
            "success": False,
            "error_type": "ExecutionError",
            "message": f"Failed to list tables: {str(ex)}",
            "suggestion": "Check database file permissions or integrity.",
        }
    finally:
        conn.close()


def execute_describe_table(table_name: str, db_path: str | None = None) -> dict[str, Any]:
    """Retrieve column details, primary keys, foreign keys, and indexes for a table."""
    if not table_name or not table_name.strip():
        return {
            "success": False,
            "error_type": "ValidationError",
            "message": "Table name must not be empty.",
            "suggestion": "Provide a valid table name from list_tables.",
        }

    clean_table_name = table_name.strip()
    escaped_table_name = clean_table_name.replace('"', '""')
    conn, err = get_connection(db_path)
    if err:
        return err

    assert conn is not None
    try:
        cursor = conn.cursor()

        # Check if table exists in sqlite_master
        cursor.execute(
            "SELECT type, sql FROM sqlite_master WHERE name = ? AND type IN ('table', 'view');",
            (clean_table_name,),
        )
        master_info = cursor.fetchone()
        if not master_info:
            return {
                "success": False,
                "error_type": "TableNotFoundError",
                "message": f"Table or view '{clean_table_name}' was not found in the database.",
                "suggestion": "Use list_tables to inspect existing tables.",
            }

        table_type = master_info["type"]
        ddl_sql = master_info["sql"]

        # Fetch columns via PRAGMA table_info
        cursor.execute(f'PRAGMA table_info("{escaped_table_name}")')
        cols = cursor.fetchall()
        columns = [
            {
                "cid": col["cid"],
                "name": col["name"],
                "type": col["type"] or "TEXT",
                "notnull": bool(col["notnull"]),
                "default_value": col["dflt_value"],
                "primary_key": bool(col["pk"]),
            }
            for col in cols
        ]

        # Fetch foreign keys
        cursor.execute(f'PRAGMA foreign_key_list("{escaped_table_name}")')
        fks = cursor.fetchall()
        foreign_keys = [
            {
                "id": fk["id"],
                "from_column": fk["from"],
                "to_table": fk["table"],
                "to_column": fk["to"],
                "on_update": fk["on_update"],
                "on_delete": fk["on_delete"],
            }
            for fk in fks
        ]

        # Fetch indexes
        cursor.execute(f'PRAGMA index_list("{escaped_table_name}")')
        idxs = cursor.fetchall()
        indexes = [
            {
                "name": idx["name"],
                "unique": bool(idx["unique"]),
                "origin": idx["origin"],
            }
            for idx in idxs
        ]

        return {
            "success": True,
            "table_name": clean_table_name,
            "type": table_type,
            "columns": columns,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
            "sql": ddl_sql,
        }
    except sqlite3.Error as ex:
        return {
            "success": False,
            "error_type": "ExecutionError",
            "message": f"Failed to describe table '{clean_table_name}': {str(ex)}",
            "suggestion": "Ensure the table name does not contain illegal characters and that the database is valid.",
        }
    finally:
        conn.close()


def execute_get_database_schema(db_path: str | None = None) -> dict[str, Any]:
    """Retrieve full database schema definition including all tables, views, and indexes."""
    conn, err = get_connection(db_path)
    if err:
        return err

    assert conn is not None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type, name;"
        )
        records = cursor.fetchall()

        schema_items = [
            {
                "type": row["type"],
                "name": row["name"],
                "table_name": row["tbl_name"],
                "sql": row["sql"],
            }
            for row in records
        ]

        return {
            "success": True,
            "database": str(resolve_database_path(db_path)[0]),
            "item_count": len(schema_items),
            "schema": schema_items,
        }
    except sqlite3.Error as ex:
        return {
            "success": False,
            "error_type": "ExecutionError",
            "message": f"Failed to retrieve database schema: {str(ex)}",
            "suggestion": "Verify that the database is readable and not corrupt.",
        }
    finally:
        conn.close()


def execute_read_query(
    query: str,
    params: list[Any] | None = None,
    max_rows: int = 1000,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Safely execute a read-only SELECT query and return structured results with row limit."""
    # 1. Validate max_rows parameter
    if max_rows < 1:
        return {
            "success": False,
            "error_type": "ValidationError",
            "message": "Parameter 'max_rows' must be a positive integer (>= 1).",
            "query": query,
            "suggestion": "Specify a positive integer for max_rows (e.g., 100 or 1000).",
        }

    # 2. Static validation of query string
    is_valid, error_msg, suggestion = validate_read_only_query(query)
    if not is_valid:
        return {
            "success": False,
            "error_type": "DisallowedQueryError",
            "message": error_msg or "Query rejected by security validation.",
            "query": query,
            "suggestion": suggestion or "Only read-only SELECT queries are allowed.",
        }

    # 3. Establish read-only connection
    conn, err = get_connection(db_path)
    if err:
        return err

    assert conn is not None
    try:
        cursor = conn.cursor()
        exec_params = params or []
        cursor.execute(query, exec_params)

        # Retrieve column names
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        # Fetch up to max_rows + 1 to detect if results exceed the limit
        rows_data = cursor.fetchmany(max_rows + 1)
        truncated = len(rows_data) > max_rows
        if truncated:
            rows_data = rows_data[:max_rows]

        # Convert sqlite3.Row objects to serializable dicts
        rows = [dict(row) for row in rows_data]

        response: dict[str, Any] = {
            "success": True,
            "query": query,
            "columns": columns,
            "row_count": len(rows),
            "rows": rows,
            "truncated": truncated,
        }

        if truncated:
            response["warning"] = (
                f"Results truncated to {max_rows} rows to prevent context window overflow. "
                "Use LIMIT and OFFSET in your SQL query for pagination."
            )

        return response
    except sqlite3.OperationalError as ex:
        err_str = str(ex)
        error_type = "SyntaxError"
        suggestion = "Review SQLite SQL syntax rules or check if table and column names exist."

        if "attempt to write a readonly database" in err_str.lower():
            error_type = "ReadOnlyViolationError"
            suggestion = "The database is opened in read-only mode. Write operations are forbidden."
        elif "no such table" in err_str.lower():
            error_type = "TableNotFoundError"
            suggestion = "Use 'list_tables' to verify available table names."
        elif "no such column" in err_str.lower():
            error_type = "ColumnNotFoundError"
            suggestion = "Use 'describe_table' to verify column names."

        return {
            "success": False,
            "error_type": error_type,
            "message": f"SQLite Operational Error: {err_str}",
            "query": query,
            "suggestion": suggestion,
        }
    except sqlite3.Error as ex:
        return {
            "success": False,
            "error_type": "ExecutionError",
            "message": f"SQLite execution failed: {str(ex)}",
            "query": query,
            "suggestion": "Check parameter binding or SQL syntax.",
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# FastMCP Tool Registrations with Tool Annotations
# ---------------------------------------------------------------------------

try:
    from mcp.types import ToolAnnotations

    READ_ONLY_TOOL_ANNOTATIONS: ToolAnnotations | None = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
except ImportError:
    READ_ONLY_TOOL_ANNOTATIONS = None


def register_tool(**kwargs: Any) -> Any:
    """Register an MCP tool with backward-compatible annotation support."""
    filtered = {k: v for k, v in kwargs.items() if v is not None}
    try:
        return mcp.tool(**filtered)
    except TypeError:
        filtered.pop("annotations", None)
        return mcp.tool(**filtered)


@register_tool(annotations=READ_ONLY_TOOL_ANNOTATIONS)
def list_tables(db_path: str | None = None) -> dict[str, Any]:
    """List all user tables and views in the SQLite database with their row count.

    Args:
        db_path: Optional path to SQLite file. If omitted, uses default database path.
    """
    return execute_list_tables(db_path=db_path)


@register_tool(annotations=READ_ONLY_TOOL_ANNOTATIONS)
def describe_table(table_name: str, db_path: str | None = None) -> dict[str, Any]:
    """Get detailed schema information for a specific table or view, including columns, primary keys, foreign keys, and indexes.

    Args:
        table_name: The name of the table or view to inspect.
        db_path: Optional path to SQLite file. If omitted, uses default database path.
    """
    return execute_describe_table(table_name=table_name, db_path=db_path)


@register_tool(annotations=READ_ONLY_TOOL_ANNOTATIONS)
def get_database_schema(db_path: str | None = None) -> dict[str, Any]:
    """Get the full CREATE DDL statements and schema definitions for all tables, views, and indexes.

    Args:
        db_path: Optional path to SQLite file. If omitted, uses default database path.
    """
    return execute_get_database_schema(db_path=db_path)


@register_tool(annotations=READ_ONLY_TOOL_ANNOTATIONS)
def read_query(
    query: str,
    params: list[Any] | None = None,
    max_rows: int = 1000,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Execute a safe, read-only SELECT query against the SQLite database.

    Args:
        query: The SQL SELECT query to execute. Mutation queries (INSERT, UPDATE, DELETE, DROP, etc.) are strictly rejected.
        params: Optional list of query parameters for prepared statements (? placeholders).
        max_rows: Maximum number of rows to return (default: 1000). Protects against context overflow.
        db_path: Optional path to SQLite file. If omitted, uses default database path.
    """
    return execute_read_query(query=query, params=params, max_rows=max_rows, db_path=db_path)


# ---------------------------------------------------------------------------
# FastMCP Resources (Direct Context Access for AI Clients)
# ---------------------------------------------------------------------------

@mcp.resource("sqlite://schema")
def database_schema_resource() -> str:
    """Resource providing the full SQLite database DDL schema."""
    schema_info = execute_get_database_schema()
    if not schema_info.get("success"):
        return f"-- Failed to retrieve schema: {schema_info.get('message')}"

    lines = [f"-- Database Schema: {schema_info.get('database')}", ""]
    for item in schema_info.get("schema", []):
        lines.append(f"{item['sql']};")
        lines.append("")
    return "\n".join(lines)


@mcp.resource("sqlite://tables")
def table_list_resource() -> str:
    """Resource listing all tables and views with row counts."""
    tables_info = execute_list_tables()
    if not tables_info.get("success"):
        return f"-- Failed to list tables: {tables_info.get('message')}"

    lines = [f"-- Tables in: {tables_info.get('database')}", ""]
    for t in tables_info.get("tables", []):
        count_str = f" ({t['row_count']} rows)" if t["row_count"] is not None else ""
        lines.append(f"- {t['name']} [{t['type']}]{count_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FastMCP Prompts (Predefined Guided Templates for AI Assistants)
# ---------------------------------------------------------------------------

@mcp.prompt()
def schema_analysis() -> str:
    """Prompt for analyzing database structure, table relationships, and optimization opportunities."""
    return (
        "Please analyze the connected SQLite database schema. "
        "Review table relationships, primary keys, foreign keys, and indexes. "
        "Suggest useful queries or identify missing indexes if applicable."
    )


@mcp.prompt()
def safe_query_assistant(user_goal: str) -> str:
    """Prompt to assist in drafting safe, optimized SELECT queries for a specific goal.

    Args:
        user_goal: Description of what data the user wants to retrieve.
    """
    return (
        f"Goal: {user_goal}\n\n"
        "Draft a safe, read-only SELECT query for this SQLite database. "
        "Follow these rules:\n"
        "1. Use explicit column names instead of SELECT * when possible.\n"
        "2. Include appropriate LIMIT and OFFSET clauses for large tables.\n"
        "3. Only read queries are allowed; avoid any data modification statements."
    )


def main() -> None:
    """Entry point for running the SQLite MCP server."""
    global DEFAULT_DB_PATH

    parser = argparse.ArgumentParser(
        description="SQLite MCP Server - Model Context Protocol for local SQLite databases."
    )
    parser.add_argument(
        "--db-path",
        "--db",
        dest="db_path",
        type=str,
        default=os.environ.get("SQLITE_DB_PATH"),
        help="Default path to local SQLite database file.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol to use (default: stdio).",
    )

    args, _ = parser.parse_known_args()
    if args.db_path:
        DEFAULT_DB_PATH = str(Path(args.db_path).expanduser().resolve())

    # FastMCP run handles stdio by default
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
