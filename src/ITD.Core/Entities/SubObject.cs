namespace ITD.Core.Entities;

public sealed record SubObject(
    Guid Id,
    Guid ParentObjectId,
    string Name,
    DateTimeOffset CreatedAt);
