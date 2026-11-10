using System.Windows;
using System.Windows.Controls;
using ITD.Core.Entities;

namespace ITD.Desktop;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        Loaded += async (_, _) => await ReloadAsync();
    }

    private async Task ReloadAsync()
    {
        try
        {
            ObjectsGrid.ItemsSource = await App.Objects.GetAllAsync();
            StatusText.Text = $"Объектов в базе: {ObjectsGrid.Items.Count}. Данные хранятся локально.";
        }
        catch (Exception ex)
        {
            StatusText.Text = "Ошибка чтения базы данных.";
            MessageBox.Show(ex.Message, "Ошибка", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private void AddObject_Click(object sender, RoutedEventArgs e)
    {
        NameBox.Focus();
        NameBox.SelectAll();
        StatusText.Text = "Заполните поля и нажмите «Сохранить».";
    }

    private async void SaveObject_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(NameBox.Text))
        {
            MessageBox.Show("Укажите наименование объекта.", "Проверка данных",
                MessageBoxButton.OK, MessageBoxImage.Warning);
            NameBox.Focus();
            return;
        }

        try
        {
            await App.Objects.CreateAsync(NameBox.Text, AddressBox.Text, CustomerBox.Text, null);
            NameBox.Clear();
            AddressBox.Clear();
            CustomerBox.Clear();
            await ReloadAsync();
            StatusText.Text = "Объект сохранён. Оригинальные документы и записи не перезаписываются.";
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Не удалось сохранить объект",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private void ObjectsGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ObjectsGrid.SelectedItem is ConstructionObject item)
            StatusText.Text = $"Выбран объект: {item.Name} · {item.Id}";
    }

    private void Objects_Click(object sender, RoutedEventArgs e) =>
        StatusText.Text = "Раздел объектов открыт.";

    private void Base_Click(object sender, RoutedEventArgs e) =>
        MessageBox.Show("Справочники, организации и документы качества будут подключены следующими вертикальными модулями.",
            "База", MessageBoxButton.OK, MessageBoxImage.Information);
}
