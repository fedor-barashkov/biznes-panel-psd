using Microsoft.Data.Sqlite;

namespace ITD.Infrastructure.Data;

public sealed class SqliteDatabase
{
    private readonly string _connectionString;

    public SqliteDatabase(string databasePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(databasePath);
        var fullPath = Path.GetFullPath(databasePath);
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
        _connectionString = new SqliteConnectionStringBuilder
        {
            DataSource = fullPath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Cache = SqliteCacheMode.Shared,
            Pooling = false,
            ForeignKeys = true,
            DefaultTimeout = 10
        }.ToString();
    }

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = FULL;
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS construction_objects (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL CHECK(length(trim(name)) > 0),
                address TEXT NULL,
                customer_name TEXT NULL,
                contractor_name TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_archived INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1))
            );
            CREATE INDEX IF NOT EXISTS ix_construction_objects_name
                ON construction_objects(name COLLATE NOCASE);
            CREATE TABLE IF NOT EXISTS sub_objects (
                id TEXT PRIMARY KEY NOT NULL,
                parent_object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE RESTRICT,
                name TEXT NOT NULL CHECK(length(trim(name)) > 0),
                created_at TEXT NOT NULL,
                UNIQUE(parent_object_id, name)
            );
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY NOT NULL,
                inn TEXT NULL,
                kpp TEXT NULL,
                ogrn TEXT NULL,
                full_name TEXT NOT NULL,
                legal_address TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_organizations_inn ON organizations(inn);
            CREATE TABLE IF NOT EXISTS document_records (
                id TEXT PRIMARY KEY NOT NULL,
                object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE RESTRICT,
                sub_object_id TEXT NULL REFERENCES sub_objects(id) ON DELETE RESTRICT,
                document_type TEXT NOT NULL,
                registration_number TEXT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                original_relative_path TEXT NULL,
                sha256 TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_document_records_object ON document_records(object_id);
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY NOT NULL,
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                details_json TEXT NULL
            );
            INSERT OR IGNORE INTO schema_migrations(version, applied_at)
                VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
            PRAGMA user_version = 1;
            """;
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<SqliteConnection> OpenConnectionAsync(CancellationToken cancellationToken = default)
    {
        var connection = new SqliteConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var pragma = connection.CreateCommand();
        pragma.CommandText = "PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 10000;";
        await pragma.ExecuteNonQueryAsync(cancellationToken);
        return connection;
    }
}
