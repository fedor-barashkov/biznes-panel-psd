namespace ITD.Core.Entities;

public sealed record ConstructionObject(
    Guid Id,
    string Name,
    string? Address,
    string? CustomerName,
    string? ContractorName,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);
