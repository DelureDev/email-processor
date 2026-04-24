# Обработка списков ДМС

Автоматическая обработка писем от страховых компаний: извлечение данных застрахованных из вложений (.xlsx / .xls / .zip) и объединение в единую мастер-таблицу.

## Возможности

- **15 страховых компаний** — РЕСО, Югория, Зетта, Альфа, Сбербанк, Согласие, ВСК, Абсолют, ПСБ, Капитал Лайф, Евроинс, Ренессанс, Ингосстрах, Лучи Здоровье, Энергогарант (+ generic-парсер для неизвестных форматов)
- **Автоопределение формата** — по отправителю или по содержимому файла
- **Пароли ZIP** — автоизвлечение паролей Зетта (месячные + поштучные) и Сбербанк
- **Определение клиники** — автоматически определяет подразделение по ключевым словам в файле и теме письма (`clinics.yaml`), добавляет колонку `Клиника` + `ID Клиники` в CSV для 1С
- **Комментарий в полис** — извлекает описание программы ДМС из файла (для нужных клиник, флаг `extract_comment: true` в `clinics.yaml`)
- **Дедупликация** — по ФИО + полис + даты обслуживания + клиника; нормализация `ё` → `е`
- **Email-отчёт** — итоги обработки + вложение `records_YYYY-MM-DD.xlsx` с новыми записями; в последний день месяца прикрепляется xlsx со всеми записями текущего месяца
- **Экспорт на сетевой диск** — ежедневный CSV + ежемесячный `master_YYYY-MM.csv` автоматически копируются в сетевую папку (SMB, userspace через `smbprotocol` или legacy через CIFS-mount) для загрузки в 1С. Таймауты не блокируют email-отчёт при недоступности сервера
- **Архивирование писем** — обработанные письма переносятся в папку "Обработанные" (настраивается в конфиге)
- **Резервное копирование** — `master.xlsx.bak` + `master.csv` создаются после каждой записи
- **Карантин** — файлы с ошибками парсинга сохраняются в `./quarantine/`
- **Аудит паролей** — отдельный лог `./logs/audit.log` для операций с паролями ZIP (без значений паролей)
- **Мониторинг** — healthcheck-пинг для контроля работы cron
- **4 режима работы** — IMAP, локальная папка, тест, dry-run

## Требования

- Python 3.10+
- LibreOffice (для конвертации .xls → .xlsx): `sudo apt install libreoffice`
- Пакеты: `pip install -r requirements.txt`

## Установка

```bash
git clone https://github.com/DelureDev/email-processor.git
cd email-processor
pip install -r requirements.txt

# Создать конфиг из шаблона
cp config.example.yaml config.yaml
nano config.yaml   # Заполнить IMAP/SMTP логин, пути, получатели
```

Учётные данные можно передавать через переменные окружения:
```yaml
imap:
  password: "${IMAP_PASSWORD}"
```

## Режимы запуска

```bash
python main.py                     # IMAP → обработка → email-отчёт
python main.py --local ./папка     # Обработка файлов из папки
python main.py --test ./папка      # Тест: разобрать и показать, без записи
python main.py --dry-run           # IMAP без записи и отправки
python main.py --no-dedup          # Отключить дедупликацию
python main.py --config path.yaml  # Альтернативный конфиг
```

## Настройка cron

```bash
crontab -e
# Добавить строку:
*/30 * * * * cd /home/user/email-processor && /usr/bin/python3 main.py >> /dev/null 2>&1
```

Для мониторинга cron — зарегистрироваться на [healthchecks.io](https://healthchecks.io) (бесплатно), вставить URL в `config.yaml`:
```yaml
healthcheck_url: "https://hc-ping.com/your-uuid-here"
```

## Единая схема данных

| Колонка | Описание |
|---------|----------|
| ФИО | Полное имя застрахованного |
| Дата рождения | ДД.ММ.ГГГГ |
| № полиса | Номер полиса ДМС |
| Начало обслуживания | Дата прикрепления |
| Конец обслуживания | Дата открепления |
| Страховая компания | Название СК |
| Страхователь | Организация-работодатель |
| Клиника | Подразделение (из `clinics.yaml`) |
| Комментарий в полис | Программа/вид обслуживания (если `extract_comment: true`) |
| Источник файла | Имя исходного файла |
| Дата обработки | Когда запись добавлена (ДД.ММ.ГГГГ) |

## Структура проекта

```
email-processor/
├── main.py              # Точка входа, CLI
├── config.example.yaml  # Шаблон конфигурации
├── fetcher.py           # IMAP подключение + перенос писем
├── detector.py          # Определение формата
├── writer.py            # Запись в мастер-таблицу
├── notifier.py          # Email-отчёты
├── clinic_matcher.py    # Определение клиники + извлечение комментария
├── clinics.yaml         # Справочник подразделений (ключевые слова)
├── zetta_handler.py     # Пароли Зетта/Сбер + ZIP
├── diagnostic.py        # Диагностика: сравнение inbox vs master
├── parsers/
│   ├── utils.py         # Общие утилиты парсеров
│   ├── reso.py          # РЕСО-Гарантия
│   ├── yugoriya.py      # ГСК Югория
│   ├── zetta.py         # Зетта Страхование
│   ├── alfa.py          # АльфаСтрахование
│   ├── sber.py          # Сбербанк Страхование
│   ├── soglasie.py      # СК Согласие
│   ├── vsk.py           # ВСК
│   ├── absolut.py       # Абсолют Страхование
│   ├── psb.py           # ПСБ Страхование
│   ├── kaplife.py       # Капитал Лайф
│   ├── euroins.py       # Евроинс
│   ├── renins.py        # Ренессанс Страхование
│   ├── ingos.py         # Ингосстрах
│   ├── luchi.py         # Лучи Здоровье
│   ├── energogarant.py  # Энергогарант
│   └── generic_parser.py # Универсальный парсер
├── requirements.txt
├── logs/
│   ├── processor.log    # Основной лог
│   └── audit.log        # Аудит операций с паролями
├── CHANGELOG.md         # История версий
└── processed_ids.db     # SQLite: отслеживание обработанных писем (мигрировано из JSON)
```

## Экспорт на сетевой диск (SMB)

Два способа на выбор — в `config.yaml` ставите нужный путь, код сам переключается.

### Вариант A: Userspace SMB (рекомендуется, v1.11.0+)

Запись идёт напрямую через Python-библиотеку `smbprotocol` — без монтирования, без ядерных таймаутов, без залипших хэндлов на сервере.

```yaml
output:
  master_file: "./output/master.xlsx"
  csv_export_folder: "\\\\SERVER\\SHARE"   # UNC-путь
  smb_credentials:
    username: "user.name"
    password: "${SMB_PASSWORD}"             # из окружения
    domain: "yourdomain.local"
```

В окружение (или в `.env` / `crontab`):
```bash
export SMB_PASSWORD="..."
```

`pip install -r requirements.txt` поставит `smbprotocol`. Больше ничего не нужно — ни `cifs-utils`, ни `/etc/fstab`, ни `mount`.

### Вариант B: Legacy CIFS mount (для обратной совместимости)

Работает, но подвержен зависаниям при проблемах на стороне SMB-сервера (D-state процессы, см. CHANGELOG v1.9.3–v1.10.17).

```bash
sudo apt install cifs-utils
sudo mkdir -p /mnt/storage
```

В `/etc/fstab`:
```
//SERVER/SHARE /mnt/storage cifs credentials=/etc/cifs-creds,iocharset=utf8,uid=adminos,file_mode=0755,dir_mode=0755,vers=2.1,soft,retrans=2,actimeo=5,_netdev,nofail 0 0
```

`/etc/cifs-creds` (0600):
```
username=user.name
password=...
domain=yourdomain.local
```

В `config.yaml`:
```yaml
output:
  csv_export_folder: "/mnt/storage"
```

После каждого запуска в сетевой папке появляются `records_YYYY-MM-DD.csv` и `master_YYYY-MM.csv`.

## Добавление новой страховой компании

1. Создать `parsers/new_company.py` с функцией `parse(filepath) -> list[dict]`
2. Добавить импорт и регистрацию в `parsers/__init__.py`
3. Добавить правило детекции в `detector.py` (sender map + keyword fallback)
4. Протестировать: `python main.py --test ./папка_с_файлом`
