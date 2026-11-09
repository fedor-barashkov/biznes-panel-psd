using System.IO;
using System.Windows;
using ITD.Infrastructure.Data;
using ITD.Infrastructure.Repositories;
using ITD.Infrastructure.Storage;

namespace ITD.Desktop;

public partial class App : Application
{
    public static SqliteDatabase Database { get; private set; } = null!;
    public static ConstructionObjectRepository Objects { get; private set; } = null!;
    public static OriginalFileStore Files { get; private set; } = null!;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        try
        {
            var root = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "ConstructionITD");
            Directory.CreateDirectory(root);

            Database = new SqliteDatabase(Path.Combine(root, "itd.db"));
            await Database.InitializeAsync();
            Objects = new ConstructionObjectRepository(Database);
            Files = new OriginalFileStore(Path.Combine(root, "files"));

            new MainWindow().Show();
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"Не удалось инициализировать локальное хранилище приложения.\n\n{ex.Message}",
                "Ошибка запуска ИТД",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
            Shutdown(-1);
        }
    }
}
