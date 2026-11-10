using ITD.Infrastructure.Data;
using ITD.Infrastructure.Repositories;
using Xunit;

namespace ITD.Infrastructure.Tests;

public sealed class ConstructionObjectRepositoryTests
{
    [Fact]
    public async Task CreateAndReadObject_PersistsObjectAndAuditEvent()
    {
        var root = Path.Combine(Path.GetTempPath(), "itd-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var database = new SqliteDatabase(Path.Combine(root, "test.db"));
            await database.InitializeAsync();
            var repository = new ConstructionObjectRepository(database);

            var created = await repository.CreateAsync(
                "Тестовый объект",
                "г. Тестовый",
                "Тестовый заказчик",
                null);

            var items = await repository.GetAllAsync();

            var saved = Assert.Single(items);
            Assert.Equal(created.Id, saved.Id);
            Assert.Equal("Тестовый объект", saved.Name);
            Assert.Equal("г. Тестовый", saved.Address);

            await using var connection = await database.OpenConnectionAsync();
            await using var command = connection.CreateCommand();
            command.CommandText = "SELECT COUNT(*) FROM audit_events WHERE entity_id = $id AND action = 'created';";
            command.Parameters.AddWithValue("$id", created.Id.ToString());
            Assert.Equal(1L, (long)(await command.ExecuteScalarAsync())!);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task CreateObject_RejectsBlankName()
    {
        var root = Path.Combine(Path.GetTempPath(), "itd-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var database = new SqliteDatabase(Path.Combine(root, "test.db"));
            await database.InitializeAsync();
            var repository = new ConstructionObjectRepository(database);
            await Assert.ThrowsAsync<ArgumentException>(() => repository.CreateAsync("  ", null, null, null));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }
    [Fact]
    public async Task SubObject_IsBoundToParentObject()
    {
        var root = Path.Combine(Path.GetTempPath(), "itd-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var database = new SqliteDatabase(Path.Combine(root, "test.db"));
            await database.InitializeAsync();
            var objects = new ConstructionObjectRepository(database);
            var parent = await objects.CreateAsync("Основной объект", null, null, null);
            var subObjects = new SubObjectRepository(database);

            await subObjects.CreateAsync(parent.Id, "Корпус 1");
            await subObjects.CreateAsync(parent.Id, "Корпус 2");

            var items = await subObjects.GetByParentAsync(parent.Id);
            Assert.Equal(2, items.Count);
            Assert.All(items, item => Assert.Equal(parent.Id, item.ParentObjectId));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task Organization_PersistsInnAndLegalDetails()
    {
        var root = Path.Combine(Path.GetTempPath(), "itd-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var database = new SqliteDatabase(Path.Combine(root, "test.db"));
            await database.InitializeAsync();
            var organizations = new OrganizationRepository(database);

            await organizations.CreateAsync(
                "ООО «Тест»", "7701234567", "770101001", "1027700000000", "г. Москва");

            var item = Assert.Single(await organizations.GetAllAsync());
            Assert.Equal("7701234567", item.Inn);
            Assert.Equal("770101001", item.Kpp);
            Assert.Equal("1027700000000", item.Ogrn);
            Assert.Equal("г. Москва", item.LegalAddress);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

}
