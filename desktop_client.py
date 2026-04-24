"""
3.1 - Единый бэкенд API: десктопный клиент подключается к тому же единому API (/api/v1),
      что и веб- и мобильный клиенты. Клиент не содержит локальной логики данных.
3.2 - Разные клиенты — разные сценарии: десктопный клиент — нативное окно ОС
      через pywebview, отображающее веб-интерфейс с ролевой логикой.
3.3 - Синхронизация данных: данные синхронизируются через единый API,
      изменения из мобильного/веб-клиента видны в десктопном и наоборот.
3.4 - Обработка ошибок: ошибки обрабатываются на уровне веб-интерфейса внутри окна.

Десктопный клиент системы управления лифтами.
Использует pywebview для отображения веб-интерфейса в нативном окне.

Установка:
    pip install pywebview

Запуск:
    1. Сначала запустите бэкенд:
       python -m uvicorn elevator_control.main:app --reload

    2. Затем запустите десктопный клиент:
       python desktop_client.py

    По умолчанию подключается к http://127.0.0.1:8000
    Можно указать другой адрес:
       python desktop_client.py --url http://192.168.1.100:8000
"""

import argparse
import sys

# 3.4 - Обработка ошибок: проверка наличия зависимости pywebview
try:
    import webview
except ImportError:
    print("Ошибка: pywebview не установлен.")
    print("Установите: pip install pywebview")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Десктопный клиент управления лифтами")
    parser.add_argument("--url", default="http://127.0.0.1:8000/clients/", help="URL бэкенда (по умолчанию http://127.0.0.1:8000/clients/)")
    parser.add_argument("--width", type=int, default=1200, help="Ширина окна")
    parser.add_argument("--height", type=int, default=800, help="Высота окна")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    if not url.endswith("/clients"):
        url = url + "/clients/"

    # 3.2 - Разные клиенты: десктопный клиент открывает веб-интерфейс в нативном окне ОС
    window = webview.create_window(
        title="Система управления лифтами — Десктоп",
        url=url,
        width=args.width,
        height=args.height,
        min_size=(800, 600),
        resizable=True,
    )

    webview.start()


if __name__ == "__main__":
    main()
