# Обработка списков ДМС

Автоматическая обработка писем от страховых компаний: извлечение данных застрахованных из вложений (.xlsx / .xls / .zip) и объединение в единую мастер-таблицу.

## Возможности

- **15 страховых компаний** — РЕСО, Югория, Зетта, Альфа, Сбербанк, Согласие, ВСК, Абсолют, ПСБ, Капитал Лайф, Евроинс, Ренессанс, Ингосстрах, Лучи Здоровье, Энергогарант (+ generic-парсер для неизвестных форматов)
- **Автоопределение формата** — по отправителю или по содержимому файла
- **Пароли ZIP** — автоизвлечение паролей Зетта (месячные + поштучные) и Сбербанк
- **Дедупликация** — по ФИО + полис + даты обслуживания
- **Email-отчёт** — итоги обработки + вложения `records_YYYY-MM-DD.xlsx` и `.csv` с новыми записями текущего запуска
- **Экспорт на сетевой диск** — ежедневный CSV автоматически копируется в сетевую папку (CIFS/SMB) для загрузки в 1С
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
| Источник файла | Имя исходного файла |
| Дата обработки | Когда запись добавлена |

## Структура проекта

```
email-processor/
├── main.py              # Точка входа, CLI
├── config.example.yaml  # Шаблон конфигурации
├── fetcher.py           # IMAP подключение
├── detector.py          # Определение формата
├── writer.py            # Запись в мастер-таблицу
├── notifier.py          # Email-отчёты
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
└── processed_ids.json   # Отслеживание обработанных писем (legacy, заменён SQLite)
```

## Экспорт на сетевой диск (SMB/CIFS)

Для автоматической выгрузки ежедневных CSV в сетевую папку (например, для 1С):

```bash
# Установить cifs-utils
sudo apt install cifs-utils

# Создать точку монтирования
sudo mkdir -p /mnt/storage

# Смонтировать шару
sudo mount -t cifs //SERVER/SHARE /mnt/storage -o username=USER,password=PASS,domain=DOMAIN,iocharset=utf8

# Добавить в /etc/fstab для автомонтирования
//SERVER/SHARE /mnt/storage cifs credentials=/etc/cifs-credentials,iocharset=utf8,uid=1000,_netdev 0 0
```

В `config.yaml`:
```yaml
output:
  master_file: "./output/master.xlsx"
  csv_export_folder: "/mnt/storage"
```

После каждого запуска файл `records_YYYY-MM-DD.csv` появится в сетевой папке.

## Добавление новой страховой компании

1. Создать `parsers/new_company.py` с функцией `parse(filepath) -> list[dict]`
2. Добавить импорт и регистрацию в `parsers/__init__.py`
3. Добавить правило детекции в `detector.py` (sender map + keyword fallback)
4. Протестировать: `python main.py --test ./папка_с_файлом`
