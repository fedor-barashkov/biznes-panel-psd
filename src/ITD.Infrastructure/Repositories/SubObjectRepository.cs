using ITD.Core.Entities;
using ITD.Infrastructure.Data;

namespace ITD.Infrastructure.Repositories;

public sealed class SubObjectRepository(SqliteDatabase database)
{
    public async Task<IReadOnlyList<SubObject>> GetByParentAsync(
        Guid parentObjectId,
        CancellationToken cancellationToken = default)
    {
        await using var connection = await database.OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, parent_object_id, name, created_at
            FROM sub_objects
            WHERE parent_object_id = $parentId
            ORDER BY name COLLATE NOCASE;
            """;
        command.Parameters.AddWithValue("$parentId", parentObjectId.ToString());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<SubObject>();
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new SubObject(
                Guid.Parse(reader.GetString(0)),
                Guid.Parse(reader.GetString(1)),
                reader.GetString(2),
                DateTimeOffset.Parse(reader.GetString(3))));
        }
        return result;
    }

    public async Task<SubObject> CreateAsync(
        Guid parentObjectId,
        string name,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        var item = new SubObject(Guid.NewGuid(), parentObjectId, name.Trim(), DateTimeOffset.UtcNow);

        await using var connection = await database.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.Transaction = (Microsoft.Data.Sqlite.SqliteTransaction)transaction;
        command.CommandText = """
            INSERT INTO sub_objects (id, parent_object_id, name, created_at)
            VALUES ($id, $parentId, $name, $createdAt);
            INSERT INTO audit_events
                (id, occurred_at, actor, action, entity_type, entity_id, details_json)
            VALUES
                ($auditId, $createdAt, 'local-user', 'created', 'sub_object', $id, NULL);
            """;
        command.Parameters.AddWithValue("$id", item.Id.ToString());
        command.Parameters.AddWithValue("$parentId", item.ParentObjectId.ToString());
        command.Parameters.AddWithValue("$name", item.Name);
        command.Parameters.AddWithValue("$createdAt", item.CreatedAt.ToString("O"));
        command.Parameters.AddWithValue("$auditId", Guid.NewGuid().ToString());
        await command.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return item;
    }
}
