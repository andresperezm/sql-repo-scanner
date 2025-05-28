# Oracle to PostgreSQL SQL Scanner

This project was cerated using ADK, it contains an agent designed to scan various types of source code files to identify embedded Oracle SQL statements. The primary goal is to assist in the analysis and migration of applications from an Oracle database backend to PostgreSQL.

## Description

Migrating database systems can be a complex task, especially when SQL queries are embedded directly within application code or configuration files. This tool helps by automatically scanning a project's codebase to locate Oracle-specific SQL. This allows developers to:

*   Identify all instances of Oracle SQL.
*   Assess the scope of changes required for a PostgreSQL migration.
*   Streamline the process of converting SQL syntax and functions.

## Features

*   **Multi-File Type Support**: Scans a variety of file types for SQL statements, including:
    *   ASP files (`.asp`)
    *   Java properties files (`.properties`)
    *   XML files (`.xml`), including MyBatis configurations
    *   SQL script files (`.sql`)
    *   C# files (`.cs`)
    *   Java files (`.java`)
*   **SQL Statement Extraction**: Identifies and extracts SQL queries from the scanned files.
*   **Analysis Output**: Generates a structured output (like `oracle-to-postgresql_analysis.jsonl`) detailing the file paths and the SQL statements found within them.

## Getting Started

This project was setup via uv command