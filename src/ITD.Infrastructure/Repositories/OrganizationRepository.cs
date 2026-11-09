using ITD.Core.Entities;
using ITD.Infrastructure.Data;

namespace ITD.Infrastructure.Repositories;

public sealed class OrganizationRepository(SqliteDatabase database)
{
    public async Task<IReadOnlyList<Organization>> GetAllAsync(CancellationToken cancellationToken = default)
    {
        await using var connection = await database.OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, inn, kpp, ogrn, full_name, legal_address, created_at, updated_at
            FROM organizations
            ORDER BY full_name COLLATE NOCASE;
            """;
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<Organization>();
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new Organization(
                Guid.Parse(reader.GetString(0)),
                reader.IsDBNull(1) ? null : reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3),
                reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                DateTimeOffset.Parse(reader.GetString(6)),
                DateTimeOffset.Parse(reader.GetString(7))));
        }
        return result;
    }

    public async Task<Organization> CreateAsync(
        string fullName,
        string? inn,
        string? kpp,
        string? ogrn,
        string? legalAddress,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(fullName);
        var now = DateTimeOffset.UtcNow;
        var item = new Organization(Guid.NewGuid(), Clean(inn), Clean(kpp), Clean(ogrn),
            fullName.Trim(), Clean(legalAddress), now, now);

        await using var connection = await database.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.Transaction = (Microsoft.Data.Sqlite.SqliteTransaction)transaction;
        command.CommandText = """
            INSERT INTO organizations
                (id, inn, kpp, ogrn, full_name, legal_address, created_at, updated_at)
            VALUES
                ($id, $inn, $kpp, $ogrn, $name, $address, $createdAt, $updatedAt);
            INSERT INTO audit_events
                (id, occurred_at, actor, action, entity_type, entity_id, details_json)
            VALUES
                ($auditId, $createdAt, 'local-user', 'created', 'organization', $id, NULL);
            """;
        command.Parameters.AddWithValue("$id", item.Id.ToString());
        command.Parameters.AddWithValue("$inn", (object?)item.Inn ?? DBNull.Value);
        command.Parameters.AddWithValue("$kpp", (object?)item.Kpp ?? DBNull.Value);
        command.Parameters.AddWithValue("$ogrn", (object?)item.Ogrn ?? DBNull.Value);
        command.Parameters.AddWithValue("$name", item.FullName);
        command.Parameters.AddWithValue("$address", (object?)item.LegalAddress ?? DBNull.Value);
        command.Parameters.AddWithValue("$createdAt", item.CreatedAt.ToString("O"));
        command.Parameters.AddWithValue("$updatedAt", item.UpdatedAt.ToString("O"));
        command.Parameters.AddWithValue("$auditId", Guid.NewGuid().ToString());
        await command.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return item;
    }

    private static string? Clean(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
