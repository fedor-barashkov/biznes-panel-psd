using ITD.Core.Entities;
using ITD.Infrastructure.Data;

namespace ITD.Infrastructure.Repositories;

public sealed class ConstructionObjectRepository(SqliteDatabase database)
{
    public async Task<IReadOnlyList<ConstructionObject>> GetAllAsync(CancellationToken cancellationToken = default)
    {
        await using var connection = await database.OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, name, address, customer_name, contractor_name, created_at, updated_at
            FROM construction_objects
            WHERE is_archived = 0
            ORDER BY name COLLATE NOCASE;
            """;
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<ConstructionObject>();
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new ConstructionObject(
                Guid.Parse(reader.GetString(0)),
                reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3),
                reader.IsDBNull(4) ? null : reader.GetString(4),
                DateTimeOffset.Parse(reader.GetString(5)),
                DateTimeOffset.Parse(reader.GetString(6))));
        }
        return result;
    }

    public async Task<ConstructionObject> CreateAsync(
        string name,
        string? address,
        string? customerName,
        string? contractorName,
        CancellationToken cancellationToken = default)
    {
        var normalizedName = name.Trim();
        ArgumentException.ThrowIfNullOrWhiteSpace(normalizedName);
        var now = DateTimeOffset.UtcNow;
        var entity = new ConstructionObject(Guid.NewGuid(), normalizedName,
            NullIfBlank(address), NullIfBlank(customerName), NullIfBlank(contractorName), now, now);

        await using var connection = await database.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.Transaction = (Microsoft.Data.Sqlite.SqliteTransaction)transaction;
        command.CommandText = """
            INSERT INTO construction_objects
                (id, name, address, customer_name, contractor_name, created_at, updated_at)
            VALUES
                ($id, $name, $address, $customer, $contractor, $created, $updated);
            INSERT INTO audit_events
                (id, occurred_at, actor, action, entity_type, entity_id, details_json)
            VALUES
                ($auditId, $created, 'local-user', 'created', 'construction_object', $id, NULL);
            """;
        command.Parameters.AddWithValue("$id", entity.Id.ToString());
        command.Parameters.AddWithValue("$name", entity.Name);
        command.Parameters.AddWithValue("$address", (object?)entity.Address ?? DBNull.Value);
        command.Parameters.AddWithValue("$customer", (object?)entity.CustomerName ?? DBNull.Value);
        command.Parameters.AddWithValue("$contractor", (object?)entity.ContractorName ?? DBNull.Value);
        command.Parameters.AddWithValue("$created", entity.CreatedAt.ToString("O"));
        command.Parameters.AddWithValue("$updated", entity.UpdatedAt.ToString("O"));
        command.Parameters.AddWithValue("$auditId", Guid.NewGuid().ToString());
        await command.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return entity;
    }

    private static string? NullIfBlank(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
