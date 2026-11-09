namespace ITD.Core.Entities;

public sealed record Organization(
    Guid Id,
    string? Inn,
    string? Kpp,
    string? Ogrn,
    string FullName,
    string? LegalAddress,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);
