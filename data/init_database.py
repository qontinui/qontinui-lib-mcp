#!/usr/bin/env python3
"""
Database initialization and testing script for qontinui-mcp.

This script:
1. Creates the SQLite database with FTS5 search
2. Applies the schema
3. Loads sample data
4. Runs performance tests
5. Validates search functionality
"""

import sqlite3
import time
from pathlib import Path
from typing import List

# File paths
SCRIPT_DIR = Path(__file__).parent
SCHEMA_FILE = SCRIPT_DIR / "schema.sql"
SAMPLE_DATA_FILE = SCRIPT_DIR / "sample_data.sql"
DB_FILE = SCRIPT_DIR / "qontinui.db"


def execute_sql_file(conn: sqlite3.Connection, filepath: Path) -> None:
    """Execute a SQL file."""
    print(f"Executing {filepath.name}...")
    with open(filepath, "r") as f:
        sql_script = f.read()
    conn.executescript(sql_script)
    conn.commit()
    print(f"  ✓ {filepath.name} executed successfully")


def init_database(force: bool = False) -> sqlite3.Connection:
    """Initialize the database with schema and sample data."""
    if DB_FILE.exists() and not force:
        print(f"Database already exists at {DB_FILE}")
        print("Use --force to recreate")
        return sqlite3.connect(DB_FILE)

    if DB_FILE.exists() and force:
        print("Removing existing database...")
        DB_FILE.unlink()

    print(f"\nInitializing database at {DB_FILE}")
    print("=" * 60)

    # Create database connection
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
    conn.execute("PRAGMA temp_store = MEMORY")

    # Apply schema
    execute_sql_file(conn, SCHEMA_FILE)

    # Load sample data
    execute_sql_file(conn, SAMPLE_DATA_FILE)

    print("=" * 60)
    print("✓ Database initialized successfully\n")

    return conn


def test_search_performance(conn: sqlite3.Connection, queries: List[str]) -> None:
    """Test FTS5 search performance."""
    print("\n" + "=" * 60)
    print("SEARCH PERFORMANCE TESTS")
    print("=" * 60)

    cursor = conn.cursor()

    for query in queries:
        # Warm up
        cursor.execute(
            """
            SELECT n.* FROM nodes n
            JOIN nodes_fts fts ON n.rowid = fts.rowid
            WHERE nodes_fts MATCH ?
        """,
            (query,),
        )
        cursor.fetchall()

        # Measure
        start = time.perf_counter()
        cursor.execute(
            """
            SELECT n.id, n.type, n.name, n.description,
                   bm25(nodes_fts) as rank
            FROM nodes n
            JOIN nodes_fts fts ON n.rowid = fts.rowid
            WHERE nodes_fts MATCH ?
            ORDER BY rank
            LIMIT 10
        """,
            (query,),
        )
        results = cursor.fetchall()
        end = time.perf_counter()

        duration_ms = (end - start) * 1000

        print(f"\nQuery: '{query}'")
        print(f"  Time: {duration_ms:.2f}ms")
        print(f"  Results: {len(results)}")
        if results:
            print(f"  Top match: {results[0]['type']} - {results[0]['name']}")
            print(f"  Rank score: {results[0]['rank']:.4f}")

        # Verify performance target
        status = "✓ PASS" if duration_ms < 20 else "✗ FAIL"
        print(f"  Status: {status} (target: < 20ms)")


def test_database_stats(conn: sqlite3.Connection) -> None:
    """Display database statistics."""
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    cursor = conn.cursor()

    # Table counts
    stats = cursor.execute("""
        SELECT 'Nodes' as table_name, COUNT(*) as count FROM nodes
        UNION ALL
        SELECT 'FTS5 Index', COUNT(*) FROM nodes_fts
        UNION ALL
        SELECT 'Templates', COUNT(*) FROM templates
        UNION ALL
        SELECT 'Node Usage', COUNT(*) FROM node_usage
    """).fetchall()

    print("\nTable Counts:")
    for stat in stats:
        print(f"  {stat['table_name']}: {stat['count']}")

    # Category breakdown
    categories = cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM nodes
        GROUP BY category
        ORDER BY count DESC
    """).fetchall()

    print("\nNodes by Category:")
    for cat in categories:
        print(f"  {cat['category']}: {cat['count']}")

    # Database file size
    if DB_FILE.exists():
        size_kb = DB_FILE.stat().st_size / 1024
        print(f"\nDatabase Size: {size_kb:.2f} KB")

    # FTS5 index info
    fts_info = cursor.execute("""
        SELECT * FROM nodes_fts WHERE nodes_fts MATCH 'click'
    """).fetchall()
    print(f"\nFTS5 Index Operational: ✓ ({len(fts_info)} matches for 'click')")


def test_common_queries(conn: sqlite3.Connection) -> None:
    """Test common query patterns."""
    print("\n" + "=" * 60)
    print("COMMON QUERY TESTS")
    print("=" * 60)

    cursor = conn.cursor()

    # 1. Get all action nodes
    print("\n1. Get all action nodes:")
    start = time.perf_counter()
    results = cursor.execute("""
        SELECT type, name FROM nodes WHERE category = 'action'
    """).fetchall()
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"  Found {len(results)} action nodes in {duration_ms:.2f}ms")
    for row in results[:3]:
        print(f"    - {row['type']}: {row['name']}")

    # 2. Get popular nodes
    print("\n2. Get popular nodes:")
    start = time.perf_counter()
    results = cursor.execute("""
        SELECT * FROM popular_nodes LIMIT 5
    """).fetchall()
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"  Top 5 popular nodes in {duration_ms:.2f}ms:")
    for row in results:
        print(f"    - {row['type']}: {row['usage_count']} uses")

    # 3. Get recent nodes
    print("\n3. Get recent nodes:")
    start = time.perf_counter()
    results = cursor.execute("""
        SELECT * FROM recent_nodes LIMIT 5
    """).fetchall()
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"  Top 5 recent nodes in {duration_ms:.2f}ms:")
    for row in results:
        print(f"    - {row['type']}: last used {row['last_used']}")

    # 4. Get popular templates
    print("\n4. Get popular templates:")
    start = time.perf_counter()
    results = cursor.execute("""
        SELECT name, category, usage_count
        FROM templates
        ORDER BY usage_count DESC
        LIMIT 5
    """).fetchall()
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"  Top 5 templates in {duration_ms:.2f}ms:")
    for row in results:
        print(f"    - {row['name']} ({row['category']}): {row['usage_count']} uses")

    # 5. Search with tags
    print("\n5. Search nodes with 'automation' tag:")
    start = time.perf_counter()
    results = cursor.execute("""
        SELECT n.type, n.name
        FROM nodes n
        JOIN nodes_fts fts ON n.rowid = fts.rowid
        WHERE nodes_fts MATCH 'tags:automation'
    """).fetchall()
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"  Found {len(results)} nodes in {duration_ms:.2f}ms")


def test_advanced_search(conn: sqlite3.Connection) -> None:
    """Test advanced FTS5 search features."""
    print("\n" + "=" * 60)
    print("ADVANCED SEARCH TESTS")
    print("=" * 60)

    cursor = conn.cursor()

    # 1. Phrase search
    print("\n1. Phrase search: '\"click element\"'")
    results = cursor.execute("""
        SELECT n.type, n.name, bm25(nodes_fts) as rank
        FROM nodes n
        JOIN nodes_fts fts ON n.rowid = fts.rowid
        WHERE nodes_fts MATCH '"click element"'
        ORDER BY rank
    """).fetchall()
    print(f"  Results: {len(results)}")
    if results:
        print(f"  Top: {results[0]['type']} (rank: {results[0]['rank']:.4f})")

    # 2. Boolean AND
    print("\n2. Boolean AND: 'click AND button'")
    results = cursor.execute("""
        SELECT n.type, n.name, bm25(nodes_fts) as rank
        FROM nodes n
        JOIN nodes_fts fts ON n.rowid = fts.rowid
        WHERE nodes_fts MATCH 'click AND button'
        ORDER BY rank
    """).fetchall()
    print(f"  Results: {len(results)}")

    # 3. Boolean OR
    print("\n3. Boolean OR: 'click OR type'")
    results = cursor.execute("""
        SELECT n.type, n.name, bm25(nodes_fts) as rank
        FROM nodes n
        JOIN nodes_fts fts ON n.rowid = fts.rowid
        WHERE nodes_fts MATCH 'click OR type'
        ORDER BY rank
        LIMIT 5
    """).fetchall()
    print(f"  Results: {len(results)} (showing top 5)")
    for row in results:
        print(f"    - {row['type']}: {row['name']} (rank: {row['rank']:.4f})")

    # 4. Boolean NOT
    print("\n4. Boolean NOT: 'click NOT right'")
    results = cursor.execute("""
        SELECT n.type, n.name, bm25(nodes_fts) as rank
        FROM nodes n
        JOIN nodes_fts fts ON n.rowid = fts.rowid
        WHERE nodes_fts MATCH 'click NOT right'
        ORDER BY rank
    """).fetchall()
    print(f"  Results: {len(results)}")

    # 5. Field-specific search
    print("\n5. Field-specific: 'name:click'")
    results = cursor.execute("""
        SELECT n.type, n.name, bm25(nodes_fts) as rank
        FROM nodes n
        JOIN nodes_fts fts ON n.rowid = fts.rowid
        WHERE nodes_fts MATCH 'name:click'
        ORDER BY rank
    """).fetchall()
    print(f"  Results: {len(results)}")
    if results:
        print(f"  Matches: {', '.join(row['type'] for row in results)}")


def run_all_tests(conn: sqlite3.Connection) -> None:
    """Run all database tests."""

    # Database stats
    test_database_stats(conn)

    # Common queries
    test_common_queries(conn)

    # Search performance
    search_queries = [
        "click",
        "button",
        "form input",
        "automation",
        "loop repeat",
        "data extract",
    ]
    test_search_performance(conn, search_queries)

    # Advanced search
    test_advanced_search(conn)

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Initialize qontinui-mcp database")
    parser.add_argument("--force", action="store_true", help="Force recreate database")
    parser.add_argument("--test", action="store_true", help="Run tests after init")
    parser.add_argument("--test-only", action="store_true", help="Only run tests (don't init)")

    args = parser.parse_args()

    if args.test_only:
        if not DB_FILE.exists():
            print(f"Error: Database not found at {DB_FILE}")
            print("Run without --test-only to create it")
            return 1
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
    else:
        conn = init_database(force=args.force)

    if args.test or args.test_only:
        run_all_tests(conn)

    conn.close()

    print(f"\nDatabase location: {DB_FILE.absolute()}")
    return 0


if __name__ == "__main__":
    exit(main())
