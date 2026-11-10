using System.Security.Cryptography;

namespace ITD.Infrastructure.Storage;

public sealed record StoredOriginal(string RelativePath, string Sha256, long Length);

public sealed class OriginalFileStore(string rootDirectory)
{
    private readonly string _root = Path.GetFullPath(rootDirectory);

    public async Task<StoredOriginal> ImportAsync(string sourcePath, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourcePath);
        if (!File.Exists(sourcePath))
            throw new FileNotFoundException("Исходный файл не найден.", sourcePath);

        Directory.CreateDirectory(_root);
        await using var source = new FileStream(sourcePath, FileMode.Open, FileAccess.Read, FileShare.Read,
            81920, FileOptions.Asynchronous | FileOptions.SequentialScan);
        var hash = await SHA256.HashDataAsync(source, cancellationToken);
        var sha256 = Convert.ToHexString(hash).ToLowerInvariant();
        var extension = Path.GetExtension(sourcePath);
        var relativePath = Path.Combine(sha256[..2], sha256 + extension.ToLowerInvariant());
        var destination = Path.GetFullPath(Path.Combine(_root, relativePath));

        if (!destination.StartsWith(_root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Недопустимый путь хранения.");

        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        if (!File.Exists(destination))
        {
            source.Position = 0;
            await using var target = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                81920, FileOptions.Asynchronous | FileOptions.WriteThrough);
            await source.CopyToAsync(target, cancellationToken);
            await target.FlushAsync(cancellationToken);
        }

        var info = new FileInfo(destination);
        return new StoredOriginal(relativePath, sha256, info.Length);
    }
}
