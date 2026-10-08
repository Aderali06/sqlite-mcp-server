"""Unit and integration tests for SQLite MCP Server."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import pytest

from src.server import (
    database_schema_resource,
    execute_describe_table,
    execute_get_database_schema,
    execute_list_tables,
    execute_read_query,
    safe_query_assistant,
    schema_analysis,
    strip_sql_comments,
    table_list_resource,
    validate_read_only_query,
)


@pytest.fixture
def sample_db(tmp_path: Path) -> Generator[str, None, None]:
    """Create a temporary populated SQLite database for testing."""
    db_file = tmp_path / "test_sample.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
    """)

    cursor.execute("""
        CREATE TABLE employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            department_id INTEGER,
            salary REAL DEFAULT 50000.0,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        );
    """)

    cursor.execute("""
        CREATE INDEX idx_employees_department ON employees(department_id);
    """)

    cursor.execute("""
        CREATE VIEW view_employee_summary AS
        SELECT e.id, e.name, e.email, d.name AS department_name
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id;
    """)

    # Insert sample data
    cursor.execute("INSERT INTO departments (name) VALUES ('Engineering'), ('Marketing');")
    cursor.execute(
        "INSERT INTO employees (name, email, department_id, salary) VALUES "
        "('Alice Smith', 'alice@example.com', 1, 95000.0), "
        "('Bob Jones', 'bob@example.com', 1, 88000.0), "
        "('Charlie Brown', 'charlie@example.com', 2, 72000.0);"
    )

    conn.commit()
    conn.close()

    yield str(db_file)


# ---------------------------------------------------------------------------
# SQL Validator Tests
# ---------------------------------------------------------------------------

class TestValidateReadOnlyQuery:
    """Test SQL query validation logic."""

    def test_valid_select_queries(self) -> None:
        valid_queries = [
            "SELECT * FROM employees;",
            "SELECT id, name FROM employees WHERE salary > 80000",
            "SELECT COUNT(*) FROM departments",
            "WITH engineering AS (SELECT * FROM employees WHERE department_id = 1) SELECT * FROM engineering;",
            "EXPLAIN QUERY PLAN SELECT * FROM employees WHERE id = 1;",
            "PRAGMA table_info('employees');",
        ]
        for query in valid_queries:
            is_valid, err_msg, suggestion = validate_read_only_query(query)
            assert is_valid is True, f"Failed on valid query: {query}. Error: {err_msg}"
            assert err_msg is None
            assert suggestion is None

    def test_strip_comments(self) -> None:
        raw_sql = "-- single line comment\nSELECT * FROM employees; /* multi-line\ncomment */"
        stripped = strip_sql_comments(raw_sql)
        assert "SELECT * FROM employees;" in stripped
        assert "comment" not in stripped

    def test_disallowed_mutation_queries(self) -> None:
        blocked_queries = [
            "INSERT INTO employees (name, email) VALUES ('Dave', 'dave@example.com')",
            "UPDATE employees SET salary = 100000 WHERE id = 1",
            "DELETE FROM employees WHERE id = 1",
            "DROP TABLE employees",
            "ALTER TABLE employees ADD COLUMN phone TEXT",
            "CREATE TABLE evil (id INT)",
            "REPLACE INTO departments (id, name) VALUES (1, 'R&D')",
            "ATTACH DATABASE 'other.db' AS other",
            "DETACH DATABASE other",
            "VACUUM",
        ]
        for query in blocked_queries:
            is_valid, err_msg, suggestion = validate_read_only_query(query)
            assert is_valid is False, f"Did not block disallowed query: {query}"
            assert err_msg is not None
            assert suggestion is not None

    def test_disallowed_pragmas(self) -> None:
        is_valid, err_msg, _ = validate_read_only_query("PRAGMA writable_schema = 1;")
        assert is_valid is False
        assert "strictly forbidden" in err_msg.lower() or "restricted" in err_msg.lower()

        is_valid, err_msg, _ = validate_read_only_query("PRAGMA query_only = 0;")
        assert is_valid is False

    def test_disallow_multiple_statements(self) -> None:
        chain_query = "SELECT * FROM employees; DROP TABLE employees;"
        is_valid, err_msg, suggestion = validate_read_only_query(chain_query)
        assert is_valid is False
        assert "Multiple SQL statements" in err_msg
        assert suggestion is not None

    def test_empty_and_whitespace_queries(self) -> None:
        for empty_q in ["", "   ", "\n\t", "-- only comment"]:
            is_valid, err_msg, _ = validate_read_only_query(empty_q)
            assert is_valid is False
            assert err_msg is not None


# ---------------------------------------------------------------------------
# Database Inspection Tool Tests
# ---------------------------------------------------------------------------

class TestListTables:
    """Test listing tables and views."""

    def test_list_tables_success(self, sample_db: str) -> None:
        result = execute_list_tables(db_path=sample_db)
        assert result["success"] is True
        assert result["table_count"] == 3

        table_names = {t["name"] for t in result["tables"]}
        assert "departments" in table_names
        assert "employees" in table_names
        assert "view_employee_summary" in table_names

        # Check row count
        emp_table = next(t for t in result["tables"] if t["name"] == "employees")
        assert emp_table["row_count"] == 3
        assert emp_table["type"] == "table"

    def test_list_tables_missing_db(self) -> None:
        result = execute_list_tables(db_path="non_existent_file.sqlite")
        assert result["success"] is False
        assert result["error_type"] == "DatabaseNotFoundError"
        assert "suggestion" in result


class TestDescribeTable:
    """Test table inspection."""

    def test_describe_existing_table(self, sample_db: str) -> None:
        result = execute_describe_table("employees", db_path=sample_db)
        assert result["success"] is True
        assert result["table_name"] == "employees"
        assert result["type"] == "table"

        col_names = [col["name"] for col in result["columns"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "email" in col_names
        assert "salary" in col_names

        # Check primary key identification
        id_col = next(c for c in result["columns"] if c["name"] == "id")
        assert id_col["primary_key"] is True

        # Check foreign keys
        assert len(result["foreign_keys"]) >= 1
        assert result["foreign_keys"][0]["to_table"] == "departments"

        # Check indexes
        index_names = [idx["name"] for idx in result["indexes"]]
        assert "idx_employees_department" in index_names

    def test_describe_non_existent_table(self, sample_db: str) -> None:
        result = execute_describe_table("non_existent_table", db_path=sample_db)
        assert result["success"] is False
        assert result["error_type"] == "TableNotFoundError"
        assert "suggestion" in result

    def test_describe_empty_table_name(self, sample_db: str) -> None:
        result = execute_describe_table("", db_path=sample_db)
        assert result["success"] is False
        assert result["error_type"] == "ValidationError"


class TestGetDatabaseSchema:
    """Test full DDL schema retrieval."""

    def test_get_database_schema(self, sample_db: str) -> None:
        result = execute_get_database_schema(db_path=sample_db)
        assert result["success"] is True
        assert result["item_count"] >= 3

        names = [item["name"] for item in result["schema"]]
        assert "departments" in names
        assert "employees" in names
        assert "view_employee_summary" in names
        assert "idx_employees_department" in names

        for item in result["schema"]:
            assert "sql" in item
            assert item["sql"] is not None


# ---------------------------------------------------------------------------
# Query Execution Tests
# ---------------------------------------------------------------------------

class TestReadQuery:
    """Test read-only query execution."""

    def test_successful_select(self, sample_db: str) -> None:
        query = "SELECT id, name, salary FROM employees WHERE salary > ? ORDER BY id ASC;"
        result = execute_read_query(query, params=[80000.0], db_path=sample_db)

        assert result["success"] is True
        assert result["row_count"] == 2
        assert result["columns"] == ["id", "name", "salary"]
        assert result["rows"][0]["name"] == "Alice Smith"
        assert result["rows"][1]["name"] == "Bob Jones"

    def test_select_from_view(self, sample_db: str) -> None:
        query = "SELECT * FROM view_employee_summary ORDER BY id ASC;"
        result = execute_read_query(query, db_path=sample_db)

        assert result["success"] is True
        assert result["row_count"] == 3
        assert result["rows"][0]["department_name"] == "Engineering"

    def test_disallowed_mutation_execution(self, sample_db: str) -> None:
        query = "DELETE FROM employees WHERE id = 1;"
        result = execute_read_query(query, db_path=sample_db)

        assert result["success"] is False
        assert result["error_type"] == "DisallowedQueryError"
        assert "suggestion" in result

    def test_syntax_error_handling(self, sample_db: str) -> None:
        query = "SELECT * FROM employees WHERE WHERE id = 1;"
        result = execute_read_query(query, db_path=sample_db)

        assert result["success"] is False
        assert result["error_type"] == "SyntaxError"
        assert "suggestion" in result

    def test_missing_table_error_handling(self, sample_db: str) -> None:
        query = "SELECT * FROM nonexistent_table;"
        result = execute_read_query(query, db_path=sample_db)

        assert result["success"] is False
        assert result["error_type"] == "TableNotFoundError"
        assert "suggestion" in result
        assert "list_tables" in result["suggestion"]

    def test_missing_column_error_handling(self, sample_db: str) -> None:
        query = "SELECT unknown_col FROM employees;"
        result = execute_read_query(query, db_path=sample_db)

        assert result["success"] is False
        assert result["error_type"] == "ColumnNotFoundError"
        assert "suggestion" in result
        assert "describe_table" in result["suggestion"]

    def test_read_query_missing_db(self) -> None:
        query = "SELECT 1;"
        result = execute_read_query(query, db_path="nonexistent.db")

        assert result["success"] is False
        assert result["error_type"] == "DatabaseNotFoundError"

    def test_max_rows_truncation(self, sample_db: str) -> None:
        # Sample DB has 3 employees. Set max_rows=2 to verify truncation
        query = "SELECT * FROM employees ORDER BY id ASC;"
        result = execute_read_query(query, max_rows=2, db_path=sample_db)

        assert result["success"] is True
        assert result["row_count"] == 2
        assert result["truncated"] is True
        assert "warning" in result
        assert "LIMIT and OFFSET" in result["warning"]

    def test_max_rows_no_truncation(self, sample_db: str) -> None:
        query = "SELECT * FROM employees ORDER BY id ASC;"
        result = execute_read_query(query, max_rows=10, db_path=sample_db)

        assert result["success"] is True
        assert result["row_count"] == 3
        assert result["truncated"] is False
        assert "warning" not in result

    def test_invalid_max_rows(self, sample_db: str) -> None:
        result = execute_read_query("SELECT 1;", max_rows=0, db_path=sample_db)
        assert result["success"] is False
        assert result["error_type"] == "ValidationError"
        assert "max_rows" in result["message"]


class TestDatabaseResolution:
    """Test resolution of database path via arguments and environment variables."""

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch, sample_db: str) -> None:
        monkeypatch.setenv("SQLITE_DB_PATH", sample_db)
        # Call without db_path, should resolve from env var
        result = execute_list_tables()
        assert result["success"] is True
        assert result["table_count"] == 3

    def test_missing_db_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SQLITE_DB_PATH", raising=False)
        result = execute_list_tables()
        assert result["success"] is False
        assert result["error_type"] == "DatabaseConfigError"

    def test_describe_view(self, sample_db: str) -> None:
        result = execute_describe_table("view_employee_summary", db_path=sample_db)
        assert result["success"] is True
        assert result["type"] == "view"
        col_names = [c["name"] for c in result["columns"]]
        assert "department_name" in col_names


class TestMcpResourcesAndPrompts:
    """Test MCP Resource and Prompt generators."""

    def test_schema_resource(self, monkeypatch: pytest.MonkeyPatch, sample_db: str) -> None:
        monkeypatch.setenv("SQLITE_DB_PATH", sample_db)
        content = database_schema_resource()
        assert "-- Database Schema:" in content
        assert "CREATE TABLE departments" in content
        assert "CREATE TABLE employees" in content

    def test_tables_resource(self, monkeypatch: pytest.MonkeyPatch, sample_db: str) -> None:
        monkeypatch.setenv("SQLITE_DB_PATH", sample_db)
        content = table_list_resource()
        assert "-- Tables in:" in content
        assert "employees" in content
        assert "departments" in content

    def test_schema_analysis_prompt(self) -> None:
        prompt_text = schema_analysis()
        assert "analyze the connected SQLite database schema" in prompt_text

    def test_safe_query_assistant_prompt(self) -> None:
        prompt_text = safe_query_assistant("Find highest earning employees")
        assert "Goal: Find highest earning employees" in prompt_text
        assert "SELECT" in prompt_text


class TestToolRegistrations:
    """Test that all 4 tools are registered with proper metadata."""

    def test_tools_registered_with_annotations(self) -> None:
        from src.server import describe_table, get_database_schema, list_tables, read_query

        # Ensure tools are callable and registered
        assert callable(list_tables)
        assert callable(describe_table)
        assert callable(get_database_schema)
        assert callable(read_query)

