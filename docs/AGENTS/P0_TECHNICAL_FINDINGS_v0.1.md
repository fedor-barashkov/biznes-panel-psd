# P0 — предварительные технические выводы для Runtime MVP

**Версия:** 0.1  
**Дата:** 2026-11-10  
**Статус:** исследовательский результат; предварительные решения требуют подтверждения техническими spike. Код Runtime не создавался.

## 1. Краткий вывод

Для первого локального MVP наиболее обоснован кандидатный стек:

- .NET 10 LTS для Runtime Core и Windows host;
- .NET Generic Host / Worker-style process для управления жизненным циклом фоновых задач;
- отдельный пользовательский процесс, запускаемый по требованию, а не Windows Service на первом этапе;
- Named Pipes с явными Windows ACL для IPC внутри одной Windows-сессии;
- SQLite на локальном диске для метаданных и очереди состояний; отдельное файловое хранилище для документов и бинарных артефактов;
- существующее WPF-приложение ИТД — один из клиентов, но не контейнер Runtime и не владелец его внутренней логики;
- версионируемые JSON Schema контракты как независимый межклиентский слой.

Это предварительный выбор направления, а не утверждённый технологический baseline. Он должен пройти SP-01—SP-07 и быть оформлен финальными ADR.

## 2. Проверка существующего GitHub-каркаса

Ветка itd-product-bootstrap содержит:
- ITD.sln с проектами ITD.Core, ITD.Infrastructure, ITD.Desktop и инфраструктурными тестами;
- ITD.Core и ITD.Infrastructure на net10.0;
- ITD.Desktop на net10.0-windows с WPF;
- SQLite через Microsoft.Data.Sqlite.Core и SQLitePCLRaw.bundle_e_sqlite3;
- global.json закрепляет SDK 10.0.100;
- CI выполняет restore, test, build и self-contained win-x64 publish с single-file и native library self-extraction.

В docs/DEV_STATUS.md отражены четыре инфраструктурных теста и успешный Windows CI. Это подтверждает сборку имеющегося каркаса на CI, но не доказывает запуск на пользовательском компьютере, работу Runtime, IPC, Windows ACL, безопасное резервирование или интеграцию с ИИ-клиентами.

**Граница повторного использования:** можно повторно использовать изученные подходы, настройки сборки и опыт Windows CI. Нельзя делать ITD.Core зависимостью независимого construction-ai-agents runtime. У приложения ИТД и платформы агентов должны быть собственные модели предметной области, жизненный цикл и версии API. Общими являются только согласованные внешние контракты и форматы обмена.

## 3. Сравнение вариантов хостинга

| Вариант | Плюсы | Минусы / риски | Предварительное решение |
|---|---|---|---|
| Runtime встроен в процесс ИТД | Меньше процессов и IPC | ИТД становится обязательным; другие клиенты не могут независимо использовать ядро; обновления и сбои связаны | Отклонить |
| Windows Service | Постоянная работа, стандартный SCM, подходит для серверного режима | Установка/управление обычно требуют административных прав; сложнее пользовательский контекст и первый запуск | Не выбирать для MVP |
| Отдельный пользовательский процесс on-demand | Независим от UI, не требует постоянной службы; подходит для одного локального пользователя; можно перезапускать и обновлять отдельно | Нужны IPC, обнаружение процесса, безопасное завершение и восстановление | **Предпочтительный вариант MVP** |
| Только запуск CLI/одноразового процесса | Простая первая проверка и автоматизация | Нет постоянно доступной очереди и локального API | Использовать как тестовый harness |

### Решение H-01 (предварительное)

Runtime запускается отдельным пользовательским процессом. ИТД и другие локальные приложения могут запрашивать его запуск и подключаться к нему. В будущем можно добавить Windows Service или серверный режим как другой Host для тех же модулей Core, не меняя бизнес-контракты.

Не устанавливать службу Windows и не требовать администратора в MVP-0.

.NET Generic Host предоставляет общий жизненный цикл, конфигурацию, DI, логирование и управляемое завершение. Windows Service — отдельный hosting option, а не обязательная архитектура ядра.

## 4. IPC и подключение клиентов

### 4.1. Локальные Windows-клиенты

Предпочтительный первый транспорт — Windows Named Pipes. Он подходит для локального обмена между процессами и позволяет применить security descriptor/DACL. Обязательные условия:
- уникальное имя канала с локальным namespace и идентификатором пользователя/экземпляра;
- ACL по принципу минимальных полномочий, а не системный default;
- запрет удалённого доступа к каналу;
- проверка пользователя и контекста клиента на серверной стороне;
- ограничение размера сообщений, тайм-ауты, correlation ID и версия контракта;
- никакого произвольного выполнения shell/команд через IPC;
- каждый запрос проходит Task Intake и policy checks.

Важно: документация Win32 предупреждает, что стандартный DACL named pipe при NULL security descriptor может предоставлять Everyone и anonymous read access. Поэтому полагаться на настройки по умолчанию запрещено. Нужен отдельный security spike на фактических .NET/Windows API, включая logon SID, impersonation и отказ неавторизованному процессу.

### 4.2. Loopback HTTP

HTTP на 127.0.0.1 может быть запасным транспортом для клиентов, которым неудобны Named Pipes, но не должен открываться в LAN по умолчанию. Потребуются случайный секрет/токен с защищённым хранением, проверка Origin/Host, защита от CSRF/DNS rebinding, ограничение методов, CORS allowlist и локальная аутентификация. Сам факт привязки к localhost не является достаточной авторизацией.

### 4.3. ChatGPT/Codex и удалённые клиенты

Локальный Named Pipe не доступен облачному ChatGPT или удалённой сессии Codex автоматически. Браузерная/облачная модель не может обращаться к произвольному IPC на компьютере пользователя только потому, что локальный Runtime запущен.

Поэтому предусматриваются разные адаптеры:
- локальный адаптер для приложения на том же компьютере (IPC или локальный stdio/MCP host, если клиент это поддерживает);
- удалённый адаптер через специально спроектированный аутентифицированный relay/gateway — только отдельной фазой, с явным согласием пользователя, allowlist операций и проверкой прав на локальной стороне.

Нельзя ради удобства подключать Runtime к публичному интернету, открывать порт в LAN или передавать долговременный локальный токен в промпт.

### Решение IPC-01 (предварительное)

Начать с Named Pipes для локальных Windows-клиентов. Абстрагировать транспорт за интерфейсом Gateway. Loopback HTTP и remote relay оставить отдельными адаптерами после threat review.

## 5. .NET и разделение проектов

Предлагаемая структура независимого репозитория:

    Construction.Agents.sln
      src/
        Construction.Agents.Contracts/
        Construction.Agents.Core/
        Construction.Agents.Runtime/
        Construction.Agents.Infrastructure/
        Construction.Agents.WindowsHost/
        Construction.Agents.Adapters.Office/
        Construction.Agents.Adapters.ITD/
        Construction.Agents.Adapters.GrandSmeta/
      tests/
        Contracts.Tests/
        Core.Tests/
        Runtime.Tests/
        Security.Tests/
        Windows.Integration.Tests/

Границы:
- Contracts — внешние схемы, версии сообщений и совместимость;
- Core — state machine, бизнес-правила и интерфейсы без Windows UI;
- Runtime — оркестрация, execution manager и lifecycle;
- Infrastructure — SQLite, filesystem, audit и реализации хранилищ;
- WindowsHost — Generic Host, IPC, Windows identity и запуск;
- Adapters — независимые подключения к клиентам и внешним системам.

Это эскиз логического разбиения; число проектов может быть сокращено после spike, но слои и направления зависимостей сохраняются.

### Решение DOTNET-01 (предварительное)

Использовать .NET 10 LTS как основной кандидат для Windows Runtime. Общие библиотеки таргетировать на net10.0, Windows Host и WPF UI — на Windows-specific TFM. Не ссылаться на WPF из Core/Contracts. Обновлять SDK и runtime на актуальные обслуживаемые patch releases.

.NET 10 находится на активной LTS-поддержке до ноября 2028 года согласно официальной политике Microsoft на дату исследования. Существующий ITD scaffold уже использует .NET 10, что снижает технологическое разнообразие в локальном Windows-контуре, но не создаёт жёсткой зависимости между репозиториями.

## 6. Хранилище и SQLite

Для одного локального пользователя SQLite подходит как кандидат для задач, состояний, транзакций и очереди; метаданных документов и редакций; provenance; локального аудита и конфигурации. Содержимое крупных PDF/DOCX/XLSX хранить отдельно, с content hash и неизменяемыми редакциями.

### Ограничения WAL

SQLite WAL позволяет читателям работать параллельно с записью, но одновременно остаётся только один writer. WAL требует, чтобы процессы находились на одном компьютере; сетевые файловые системы не поддерживаются для такого режима. Следовательно:
- база — только на локальном диске, не в общей сетевой папке/OneDrive/SMB;
- конкурентные записи проходят через один контролируемый Data Access Layer/очередь;
- короткие транзакции, busy timeout, checkpoint monitoring;
- тесты аварийного завершения и блокировок обязательны.

### Резервное копирование

Не копировать работающий .db файл внешним файловым копированием без согласованной процедуры. Предпочесть SQLite Online Backup API или VACUUM INTO, затем:
- проверить открытие копии;
- выполнить integrity_check;
- сверить количество и связность ключевых записей;
- проверить хеши всех файловых объектов;
- восстановить копию в отдельный каталог и провести smoke tests;
- вести журнал backup/restore и хранить несколько поколений.

### Решение DATA-01 (предварительное)

SQLite + локальное файловое хранилище допустимы для MVP-0/1 одного компьютера. Не размещать WAL database на сетевом диске. Не считать существующие тесты SQLite доказательством полноценного backup/restore.

## 7. Упаковка и обновления

| Вариант | Плюсы | Риски | Предварительное решение |
|---|---|---|---|
| Framework-dependent | Маленький пакет | Требует установленный нужный runtime | Не основной вариант |
| Self-contained win-x64 | Не требует отдельно установленного .NET Runtime | Больший пакет; встроенный runtime обновляется вместе с приложением | Предпочтительно |
| Single-file publish | Удобно передавать один EXE | Native библиотеки могут извлекаться во временный каталог; не всякая библиотека совместима; не заменяет installer | Проверить на чистой Windows |
| MSIX | Чистая установка/удаление, подпись, обновления | Package identity и ограничения packaged app; Named Pipes имеют особенности межпакетного доступа | Не утверждать для MVP-0 |
| MSI/обычный installer | Гибкий контроль путей, служб, обновлений | Требует разработки/подписи установщика и тестов удаления/обновления | Исследовать на P5 |

Для MVP-0 сначала нужен воспроизводимый self-contained win-x64 пакет и сценарий запуска без администратора. Выбор MSIX/MSI и installer tooling отложить до проверки требований к автозапуску, обновлению и интеграции с Windows.

Single-file — формат публикации, а не гарантия «один файл и ничего больше»: при включении native library self-extraction должны быть проверены права на extraction directory, отсутствие подмены библиотек и поведение антивируса/EDR.

## 8. Сопоставление с планом P0

| Spike | Что уже известно | Что осталось доказать |
|---|---|---|
| SP-01 Windows lifecycle | .NET Worker/Generic Host поддерживает длительный процесс и Windows Service hosting | пользовательский on-demand host, запуск/остановка, автозапуск, права, crash recovery |
| SP-02 Local API/IPC | Named Pipes подходят для IPC и поддерживают security descriptors | .NET ACL implementation, logon SID, запрет удалённого доступа, отказ постороннему клиенту |
| SP-03 Storage | ITD scaffold уже использует SQLite/WAL | contention, crash recovery, Online Backup API, integrity and restore |
| SP-04 Identity/keys/audit | Trust Boundary spec определяет требования | DPAPI/Windows credential storage, signed permit, nonce store, tamper-evident audit |
| SP-05 Model Gateway | .NET Generic Host подходит для DI/lifecycle | провайдерные интерфейсы, privacy classification, локальная модель, timeout/retry |
| SP-06 File ingestion | Runtime contracts допускают provenance | benchmark реальных обезличенных документов, OCR accuracy и безопасная обработка |
| SP-07 Contract compatibility | JSON Schema и fixtures уже валидируются CI | version negotiation, schema evolution, backward compatibility tests |

**P0 пока не завершён.** Документ закрывает предварительное кабинетное сравнение архитектурных вариантов, но не заменяет воспроизводимые прототипы SP-01—SP-07.

## 9. Следующий технический spike

Приоритет — **SP-02: безопасный локальный IPC**, потому что он определяет, как независимое ядро смогут использовать ИТД и локальные приложения, не открывая сетевой доступ.

Минимальный прототип должен:
1. запустить сервер Named Pipe от обычного пользователя;
2. разрешить подключение только ожидаемому security principal;
3. отклонить другой локальный пользователь и неавторизованный процесс;
4. доказать отсутствие удалённого подключения;
5. передать versioned request/response с correlation ID;
6. обработать malformed/oversized message, timeout, cancellation и разрыв соединения;
7. записать аудит подключения без секретов;
8. пройти автоматические Windows integration tests.

До успешного результата IPC-01 остаётся предварительным решением.

## 10. Официальные источники

1. Microsoft, [.NET Support Policy](https://dotnet.microsoft.com/en-us/platform/support/policy) — версии, LTS/STS и даты поддержки.
2. Microsoft, [.NET Generic Host](https://learn.microsoft.com/en-us/dotnet/core/extensions/generic-host) — lifecycle, DI, logging и hosted services.
3. Microsoft, [Create Windows Service using BackgroundService](https://learn.microsoft.com/en-us/dotnet/core/extensions/windows-service) — Windows Service hosting и single-file publish.
4. Microsoft, [WPF overview](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/overview/) — WPF работает только на Windows.
5. Microsoft, [Interprocess communication](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication) и [Named Pipe Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights) — IPC и ACL.
6. Microsoft, [Single-file deployment](https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/overview) — self-contained и ограничения single-file.
7. Microsoft, [MSIX overview](https://learn.microsoft.com/en-us/windows/msix/overview) — упаковка, identity и особенности контейнеризации.
8. SQLite, [Write-Ahead Logging](https://www.sqlite.org/wal.html) — ограничения WAL и конкурентности.
9. SQLite, [Online Backup API](https://www.sqlite.org/backup.html) — согласованное резервирование работающей БД.

**Итог:** наиболее перспективен отдельный .NET 10 пользовательский Runtime process с Named Pipes и локальной SQLite, при строгом отделении от WPF-приложения ИТД. Это рекомендация для прототипирования, а не окончательное утверждение стека и не подтверждение работающего Runtime.
