# SP-02 — технические заметки реализации для .NET 10 (v0.1)

**Статус:** исследовательская записка по API. Код прототипа не написан; ни один IPC-тест не выполнен.

## 1. Вывод исследования

Для Windows Named Pipes в .NET 10 доступны управляемые API для ACL, создания потока и клиентского impersonation. Однако у публичного перечисления `PipeOptions` нет флага, эквивалентного Win32 `PIPE_REJECT_REMOTE_CLIENTS` (0x00000008). Поэтому использование только `NamedPipeServerStream` / `NamedPipeServerStreamAcl.Create` само по себе не доказывает запрет удалённых подключений.

Документация Win32 отдельно определяет:
- `PIPE_ACCEPT_REMOTE_CLIENTS = 0`: удалённые клиенты могут подключаться, если проходят security descriptor;
- `PIPE_REJECT_REMOTE_CLIENTS = 0x00000008`: удалённые клиенты автоматически отклоняются.

Общая документация Named Pipes дополнительно рекомендует для локального канала запрещать доступ SID `NT AUTHORITY\\NETWORK` либо использовать local RPC. Для spike требуется проверка обоих механизмов и выбор на основании воспроизводимого теста.

## 2. Проверенные API .NET 10

| Задача | API | Вывод |
|---|---|---|
| Создать pipe с ACL | `NamedPipeServerStreamAcl.Create(..., PipeSecurity, ...)` | Поддерживается .NET 6–10; ACL передаётся явно |
| Создать правила ACL | `PipeSecurity`, `PipeAccessRule`, `SecurityIdentifier` | Поддерживает DACL и отдельные правила доступа |
| Получить identity клиента | `NamedPipeServerStream.RunAsClient(...)` + `WindowsIdentity.GetCurrent(true)` | Проверять OS impersonation context; отсутствие impersonation identity означает отказ |
| Узнать имя клиента | `GetImpersonationUserName()` | Диагностика, не использовать как единственную проверку полномочий |
| Асинхронное подключение | `WaitForConnectionAsync(CancellationToken)`, `ConnectAsync(timeout, CancellationToken)` | Есть отмена и тайм-аут |
| Обернуть native pipe handle | `NamedPipeServerStream(PipeDirection, bool, bool, SafePipeHandle)` | Позволяет совместить Win32 создание канала с .NET Stream API |

### Важная особенность CurrentUserOnly

Если при вызове `NamedPipeServerStreamAcl.Create` включён `PipeOptions.CurrentUserOnly`, переданный `PipeSecurity` игнорируется; создаётся security descriptor с текущим пользователем как единственным владельцем с полным доступом. Поэтому:
- не сочетать `CurrentUserOnly` с тестом custom DACL и не считать, что переданные ACL-правила применились;
- для проверки явного DACL использовать отдельный режим без `CurrentUserOnly`;
- если продукту нужен строго тот же Windows account, отдельно сравнить простой `CurrentUserOnly` профиль с custom ACL профилем.

## 3. Предлагаемые варианты реализации для spike

### Вариант A — managed ACL + запрет NETWORK SID

1. Создать `PipeSecurity` с явным DACL.
2. Разрешить только SID пользователя/требуемой группы.
3. Явно исключить `NT AUTHORITY\\NETWORK` (SID S-1-5-2) и проверить канонический итоговый ACL.
4. Создать сервер через `NamedPipeServerStreamAcl.Create`, не включая `CurrentUserOnly`.
5. Проверить доступ с локального разрешённого principal, второго локального пользователя и тестовой удалённой Windows VM.

Плюс: меньше native interop. Ограничение: надёжность запрета remote должна быть подтверждена именно на целевых Windows-конфигурациях; нельзя делать вывод только по содержимому ACL.

### Вариант B — Win32 CreateNamedPipeW + PIPE_REJECT_REMOTE_CLIENTS

1. Создать security descriptor из проверенного `PipeSecurity` и передать его через `SECURITY_ATTRIBUTES`.
2. Вызвать `CreateNamedPipeW` с `PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED` и `PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS` (конкретные флаги и режимы сверить с фактическим кодом и тестом).
3. Обернуть успешный native handle в `SafePipeHandle`, затем в `NamedPipeServerStream` через публичный конструктор.
4. Проверить владение handle, закрытие при исключениях, корректность overlapped I/O и повторное создание экземпляров.
5. Отдельно проверить защиту от pipe-name squatting: первая инстанция должна создаваться с first-instance семантикой или эквивалентной защитой; не допускать подключения к подменённому каналу.

Плюс: используется документированный Win32 remote-client reject flag. Минус: больше P/Invoke и ручного управления native handle; это увеличивает поверхность ошибок и требует отдельного QA.

### Решение для эксперимента

Реализовать оба минимальных варианта только в изолированном spike и сравнить. Если вариант A не доказывает remote rejection на тестовой VM, использовать вариант B либо отклонить Named Pipes. Не переносить native interop в production до независимого QA и ADR IPC-01.

## 4. Проверка identity

- Сервер получает client identity из impersonation context, а не из JSON.
- Получение SID выполняется внутри синхронного callback `RunAsClient`; внутри него получить `WindowsIdentity.GetCurrent(true)` и проверить ненулевую identity и SID.
- Вне callback нельзя использовать process identity сервера как будто это identity клиента.
- `GetImpersonationUserName()` — диагностическое поле, не замена SID-based policy check.
- Не выполнять файловые операции от имени клиента в spike; только получить и записать минимальный идентификатор principal.
- Ошибка impersonation, пустой SID или неожиданный principal — fail closed.

## 5. Framing и устойчивость

- Использовать byte-mode с явным length-prefix (например, 4-байтовая длина в network byte order) и строгим верхним лимитом до выделения памяти.
- Читать префикс полностью, валидировать длину, затем читать ровно заданное число байт; EOF до завершения — malformed/incomplete frame.
- Ограничить одновременно обрабатываемые подключения, общий бюджет времени и размер ответа.
- Каждому запросу — request_id и correlation_id; повтор ID в spike фиксируется и отклоняется как дубликат тестового сообщения, но транспорт не выполняет бизнес-операций.
- Unknown protocol version/type, malformed payload и oversize request завершают только запрос/соединение, не весь host.
- Логи не содержат payload целиком, токены, SID в открытом виде или персональные данные; использовать маскированный principal reference.

## 6. Обязательные тесты и доказательства

Сохранить исходную матрицу IPC-001—IPC-016. Для IPC-006 дополнительно:
- локальная попытка подключения через имя pipe на удалённом компьютере;
- проверка Win32 флага `PIPE_REJECT_REMOTE_CLIENTS` при native варианте;
- тест DACL с `NT AUTHORITY\\NETWORK` при managed варианте;
- зафиксировать, какой механизм реально использовался и почему результат означает отказ.

Тесты IPC-003 и IPC-006 требуют второй локальной учётной записи и отдельной Windows VM/машины; если среда не предоставляет их, результат только BLOCKED. Успех локального CI не заменяет эти проверки.

Каждый прогон сохраняет: commit SHA, Windows edition/build, архитектуру, .NET SDK/runtime, способ создания pipe, фактический DACL, test ID, exit code, лог без секретов и итог PASS/FAIL/BLOCKED/NOT_RUN.

## 7. Источники Microsoft

- [NamedPipeServerStreamAcl.Create (.NET 10)](https://learn.microsoft.com/en-us/dotnet/api/system.io.pipes.namedpipeserverstreamacl.create)
- [PipeSecurity (.NET 10)](https://learn.microsoft.com/en-us/dotnet/api/system.io.pipes.pipesecurity?view=net-10.0)
- [PipeSecurity.AddAccessRule (.NET 10)](https://learn.microsoft.com/en-us/dotnet/api/system.io.pipes.pipesecurity.addaccessrule?view=net-10.0)
- [NamedPipeServerStream (.NET 10), включая SafePipeHandle constructor](https://learn.microsoft.com/en-us/dotnet/api/system.io.pipes.namedpipeserverstream?view=net-10.0)
- [WindowsIdentity.GetCurrent (.NET 10)](https://learn.microsoft.com/en-us/dotnet/api/system.security.principal.windowsidentity.getcurrent)
- [NamedPipeClientStream.ConnectAsync (.NET 10)](https://learn.microsoft.com/en-us/dotnet/api/system.io.pipes.namedpipeclientstream.connectasync?view=net-10.0)
- [Win32 CreateNamedPipeA: PIPE_REJECT_REMOTE_CLIENTS](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea)
- [Win32 Named Pipes: local-only guidance](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipes)
- [Win32 Named Pipe Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)

## 8. Ограничения

Это исследование публичных API и проектирование эксперимента. Оно не является доказательством безопасной реализации. Нужны исходный код, Windows integration tests, испытание двух principals, remote VM test, проверка native handle lifecycle и независимая QA-проверка.
