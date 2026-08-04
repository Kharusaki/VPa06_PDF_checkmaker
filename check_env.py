#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль проверки и автоматической установки зависимостей.
Проверяет: Python-пакеты (pandas, weasyprint, fpdf2) и системные библиотеки (GTK3, Cairo, Pango, GLib).
"""

import sys
import os
import subprocess
import importlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Информация о пакетах
# ---------------------------------------------------------------------------

PYTHON_PACKAGES = {
    "pandas": {
        "pip": "pandas>=2.0.0",
        "description": "Библиотека для чтения и обработки CSV/JSON файлов с данными чеков",
        "import_name": "pandas",
    },
    "weasyprint": {
        "pip": "weasyprint>=60.0",
        "description": "Генерация PDF из HTML-шаблонов (основной рендер)",
        "import_name": "weasyprint",
    },
    "fpdf2": {
        "pip": "fpdf2>=2.8.0",
        "description": "Альтернативный генератор PDF (fallback, если WeasyPrint не работает)",
        "import_name": "fpdf",
    },
}

# Системные библиотеки (GTK3-рантайм)
GTK_PACKAGES = [
    {
        "name": "GTK3 Runtime",
        "pip": "gobject-introspection",  # метка для поиска
        "description": "Графическая библиотека GTK3 — основа рендеринга WeasyPrint",
        "check_dlls": ["libgobject-2.0-0.dll", "libgtk-3-0.dll"],
        "install_guide": "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Archive/releases",
    },
    {
        "name": "Cairo",
        "pip": "cairo",
        "description": "Библиотека векторной графики — используется WeasyPrint для рисования PDF",
        "check_dlls": ["libcairo-2.dll"],
        "install_guide": "Входит в GTK3 Runtime",
    },
    {
        "name": "Pango",
        "pip": "pango",
        "description": "Библиотека рендеринга текста — поддержка кириллицы и сложных шрифтов",
        "check_dlls": ["libpango-1.0-0.dll"],
        "install_guide": "Входит в GTK3 Runtime",
    },
    {
        "name": "GLib",
        "pip": "glib",
        "description": "Базовая библиотека — основа GTK3 и gobject",
        "check_dlls": ["libglib-2.0-0.dll"],
        "install_guide": "Входит в GTK3 Runtime",
    },
    {
        "name": "HarfBuzz",
        "pip": "harfbuzz",
        "description": "Библиотека разметки текста — используется Pango для корректного отображения символов",
        "check_dlls": ["libharfbuzz-0.dll"],
        "install_guide": "Входит в GTK3 Runtime",
    },
    {
        "name": "Freetype",
        "pip": "freetype",
        "description": "Библиотека рендеринга шрифтов — поддерживает кириллицу в PDF",
        "check_dlls": ["libfreetype-6.dll"],
        "install_guide": "Входит в GTK3 Runtime",
    },
]

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def _get_site_packages() -> Path:
    """Возвращает путь к директории site-packages текущего Python."""
    import site
    paths = site.getsitepackages()
    if paths:
        return Path(paths[0])
    # Fallback для виртуального env
    return Path(sys.prefix, "Lib", "site-packages")


def _get_gtk_search_paths() -> list:
    """Возвращает директории для поиска GTK DLL."""
    paths = []

    # Site-packages (пакет pygobject ставит DLL туда)
    sp = _get_site_packages()
    paths.append(sp)

    # venv/Lib/site-packages/gi/
    gi_dir = sp / "gi"
    if gi_dir.exists():
        paths.append(gi_dir)

    # PATH
    for p in os.environ.get("PATH", "").split(os.pathsep):
        paths.append(Path(p))

    return paths


# ---------------------------------------------------------------------------
# Проверка
# ---------------------------------------------------------------------------


def check_python_packages() -> dict:
    """
    Проверяет установленные Python-пакеты.
    Возвращает {package_name: {"installed": bool, "pip": str}}.
    """
    results = {}
    for pkg_name, info in PYTHON_PACKAGES.items():
        try:
            importlib.import_module(info["import_name"])
            results[pkg_name] = {"installed": True, "pip": info["pip"]}
        except (ImportError, OSError):
            # OSError возникает при импорте weasyprint без GTK DLL
            results[pkg_name] = {"installed": False, "pip": info["pip"]}
    return results


def check_system_libraries() -> list:
    """
    Проверяет наличие системных DLL (GTK3-рантайм, Cairo, Pango и т.д.).
    Возвращает список словарей {name, description, installed, dlls}.
    """
    search_paths = _get_gtk_search_paths()

    results = []
    for pkg in GTK_PACKAGES:
        installed = False
        found_dlls = []
        for dll in pkg["check_dlls"]:
            for sp in search_paths:
                if (sp / dll).exists():
                    installed = True
                    found_dlls.append(dll)
                    break

        results.append({
            "name": pkg["name"],
            "description": pkg["description"],
            "installed": installed,
            "found_dlls": found_dlls,
            "install_guide": pkg["install_guide"],
        })
    return results


# ---------------------------------------------------------------------------
# Установка
# ---------------------------------------------------------------------------


def install_python_packages(failed: list) -> bool:
    """
    Устанавливает недостающие Python-пакеты через pip.
    failed — список package_name из check_python_packages.
    Возвращает True при успехе.
    """
    print("\n  📦  Установлю недостающие Python-пакеты через pip...")
    commands = []
    for pkg_name in failed:
        pip_spec = PYTHON_PACKAGES[pkg_name]["pip"]
        commands.append(pip_spec)
        print(f"    → {pip_spec}: {PYTHON_PACKAGES[pkg_name]['description']}")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade"] + commands,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print("  ✓  Python-пакеты установлены.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗  Ошибка установки: {e}")
        return False


def show_install_guide() -> str:
    """Возвращает инструкцию по установке GTK3 Runtime для Windows."""
    guide = GTK_PACKAGES[0]  # GTK3 Runtime
    return (
        f"\n  ⚙  Для установки GTK3 Runtime (Cairo, Pango, GLib и др.):\n\n"
        f"  1.  Откройте ссылку: {guide['install_guide']}\n"
        f"  2.  Скачайте файл 'gtk3-runtime-*.zip' (последняя версия)\n"
        f"  3.  Распакуйте в: {Path.cwd() / 'gtk-runtime'}\n"
        f"  4.  Скрипт автоматически найдёт библиотеки при следующем запуске\n\n"
        f"  Или установите через Chocolatey:\n"
        f"    choco install gtk3\n"
    )


# ---------------------------------------------------------------------------
# Главный интерфейс
# ---------------------------------------------------------------------------


def check_and_prompt_install() -> bool:
    """
    Проверяет все зависимости. Если что-то отсутствует — показывает список
    и предлагает автоматическую установку.
    Возвращает True, если всё OK или установка выполнена.
    """
    py_results = check_python_packages()
    sys_results = check_system_libraries()

    missing_py = [k for k, v in py_results.items() if not v["installed"]]
    missing_sys = [r for r in sys_results if not r["installed"]]

    if not missing_py and not missing_sys:
        print("  ✓  Все зависимости установлены.")
        return True

    # ── Есть что-то недостающее — показываем пользователю ──
    print("\n" + "─" * 60)
    print("  🔍  Проверка зависимостей")
    print("─" * 60)

    # Python-пакеты
    if missing_py:
        print("\n  ❌  Не установлены Python-пакеты:")
        for pkg_name in missing_py:
            info = PYTHON_PACKAGES[pkg_name]
            print(f"    • {pkg_name}: {info['description']}")
            print(f"      pip install {info['pip']}")

    # Системные библиотеки
    if missing_sys:
        print("\n  ❌  Не найдены системные библиотеки:")
        for pkg in missing_sys:
            print(f"    • {pkg['name']}: {pkg['description']}")
            if pkg.get("found_dlls"):
                print(f"      (найдены DLL: {', '.join(pkg['found_dlls'])})")

    # ── Предложение помощи ──
    has_py = bool(missing_py)
    has_sys = bool(missing_sys)

    if has_py:
        print(f"\n  💡  Установить {', '.join(missing_py)} через pip? (y/n): ", end="")
        choice = input().strip().lower()
        if choice in ("y", "yes", "да", "д"):
            if not install_python_packages(missing_py):
                print("  ⚠  Установка не удалась. Попробуйте вручную:")
                for pkg_name in missing_py:
                    print(f"    pip install {PYTHON_PACKAGES[pkg_name]['pip']}")
                return False
        else:
            print("  ⏭  Пропускаю установку Python-пакетов.")

    if has_sys:
        print("\n  ⚙  Системные библиотеки (GTK3 Runtime, Cairo, Pango, GLib, HarfBuzz, Freetype)")
        print("  не найдены. Это технические библиотеки — они безопасны,")
        print("  не несут вреда компьютеру и нужны только для корректной")
        print("  генерации PDF через WeasyPrint.")
        print()
        print("  💡  Рекомендую установить GTK3 Runtime автоматически:")
        print(f"      {show_install_guide().strip()}")
        print("  Установить? (y/n): ", end="")
        choice = input().strip().lower()
        if choice in ("y", "yes", "да", "д"):
            print("  ⚠  Автоматическая установка GTK3 Runtime невозможна.")
            print("  Пожалуйста, выполните установку вручную по инструкции выше.")
            return False
        else:
            print("  ⏭  Пропускаю системные библиотеки.")
            print("  ℹ  Будет использован fpdf2 (fallback) — без кириллицы в PDF.")

    return True


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


def run_check() -> bool:
    """
    Запускает проверку зависимостей.
    Если всё ОК — возвращает True.
    Если что-то пропущено — выводит предупреждение, но не блокирует.
    """
    print("\n  🔍  Проверка зависимостей...")

    py_results = check_python_packages()
    sys_results = check_system_libraries()

    missing_py = [k for k, v in py_results.items() if not v["installed"]]
    missing_sys = [r for r in sys_results if not r["installed"]]

    if not missing_py and not missing_sys:
        print("  ✓  Все зависимости установлены.")
        return True

    # Если что-то пропущено — пробуем установить автоматически
    success = True

    if missing_py:
        print(f"  ⚠  Не хватает Python-пакетов: {', '.join(missing_py)}")
        print("  📦  Попытка автоматической установки...")
        success = install_python_packages(missing_py)

    if missing_sys:
        print(f"  ⚠  Не найдены системные библиотеки: {', '.join(p['name'] for p in missing_sys)}")
        print("  ℹ  Будет использован fpdf2 (fallback) для генерации PDF.")

    return success


if __name__ == "__main__":
    run_check()
