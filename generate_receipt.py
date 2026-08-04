#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор кассовых чеков ФНС РФ 2026.

CLI-инструмент для генерации printable PDF-файлов кассовых чеков
по HTML-шаблонам из CSV/JSON данных. Поддержка кириллицы,
редактирование чека перед печатью, автооткрытие PDF.
"""

import sys
import os
import csv
import json
import subprocess

# ── Кодировка консоли: принудительно UTF-8 ──────────────────────────
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# ---------------------------------------------------------------------------
# Константы путей
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"

# ---------------------------------------------------------------------------
# Проверка зависимостей (запускается на старте)
# ---------------------------------------------------------------------------


def run_environment_check() -> bool:
    """
    Запускает проверку и автоматическую установку необходимых библиотек.
    Возвращает True, если всё OK.
    """
    from check_env import run_check as _check
    return _check()

# Минимальные обязательные placeholders в HTML-шаблоне
REQUIRED_PLACEHOLDERS = [
    "{{ seller_name }}",
    "{{ seller_inn }}",
    "{{ seller_address }}",
    "{{ invoice_id }}",
    "{{ invoice_date }}",
    "{{ invoice_time }}",
    "{{ total }}",
    "{{ total_pay }}",
]

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def print_banner():
    """Выводит приветственный баннер."""
    print("\n" + "=" * 60)
    print("       PDF Receipt Generator — Генератор кассовых чеков")
    print("       Поддержка кириллицы | WeasyPrint | ФНС РФ 2026")
    print("=" * 60)


def print_menu(items: List[str], title: str = "Доступные варианты") -> int:
    """
    Выводит нумерованное меню и запрашивает выбор пользователя.
    Возвращает индекс выбранного элемента (0-based).
    """
    print(f"\n{title}:")
    print("-" * 40)
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    print(f"  {len(items) + 1}. ← Назад / Выход")
    print("-" * 40)

    while True:
        try:
            choice = input("Ваш выбор (номер): ").strip()
            num = int(choice)
            if 1 <= num <= len(items) + 1:
                return num - 1
            print("⚠  Введите число от 1 до", len(items) + 1)
        except ValueError:
            print("⚠  Введите корректный номер.")
        except EOFError:
            print("\n  ⚠  Pipe-ввод завершён.")
            return len(items)  # Выход


def load_csv_data(filepath: Path) -> List[Dict[str, str]]:
    """Парсит CSV-файл (UTF-8 с BOM или без)."""
    rows = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def load_json_data(filepath: Path) -> List[Dict[str, str]]:
    """Парсит JSON-файл (массив объектов)."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [dict(item) for item in data]
    return [data]


def load_all_data_files() -> List[Tuple[Path, str, List[Dict[str, str]]]]:
    """
    Сканирует DATA_DIR и загружает все CSV и JSON файлы.
    Возвращает список кортежей: (путь, тип, данные).
    """
    results = []

    # Собираем уникальные файлы через case-insensitive glob
    csv_files = set()
    for pattern in ["*.csv", "*.CSV", "*.Csv"]:
        csv_files.update(DATA_DIR.glob(pattern))

    json_files = set()
    for pattern in ["*.json", "*.JSON", "*.Json"]:
        json_files.update(DATA_DIR.glob(pattern))

    for fp in sorted(csv_files):
        try:
            data = load_csv_data(fp)
            results.append((fp, "CSV", data))
            print(f"  ✓  Загружен CSV: {fp.name} ({len(data)} записей)")
        except Exception as e:
            print(f"  ✗  Ошибка CSV {fp.name}: {e}")

    for fp in sorted(json_files):
        try:
            data = load_json_data(fp)
            results.append((fp, "JSON", data))
            print(f"  ✓  Загружен JSON: {fp.name} ({len(data)} записей)")
        except Exception as e:
            print(f"  ✗  Ошибка JSON {fp.name}: {e}")

    return results


def load_all_templates() -> List[Tuple[Path, str]]:
    """
    Сканирует TEMPLATES_DIR и загружает все HTML-файлы.
    Возвращает список кортежей: (путь, название).
    """
    results = []
    for fp in sorted(TEMPLATES_DIR.glob("*.html")):
        try:
            html_content = fp.read_text(encoding="utf-8")
            results.append((fp, fp.name))
            print(f"  ✓  Загружен шаблон: {fp.name}")
        except Exception as e:
            print(f"  ✗  Ошибка шаблона {fp.name}: {e}")
    return results


def validate_html_placeholders(html_content: str) -> Tuple[bool, List[str]]:
    """
    Проверяет HTML на наличие минимальных обязательных placeholders.
    Возвращает (есть_всё, список_отсутствующих).
    """
    missing = []
    for ph in REQUIRED_PLACEHOLDERS:
        if ph not in html_content:
            missing.append(ph)
    return len(missing) == 0, missing


def group_csv_items_by_invoice(data: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    """
    Для CSV: группирует строки по invoice_id.
    Возвращает словарь {invoice_id: {общие_поля, items: [список товаров]}}.
    """
    groups: Dict[str, Dict[str, Any]] = {}

    for row in data:
        inv_id = row.get("invoice_id", "UNKNOWN")

        if inv_id not in groups:
            # Копируем общие поля (без полей товаров)
            item_fields = {"product", "price", "qty", "vat_rate", "total_incl_vat"}
            common = {k: v for k, v in row.items() if k not in item_fields}
            groups[inv_id] = {"common": common, "items": []}

        # Добавляем товар
        groups[inv_id]["items"].append({
            "product": row.get("product", "—"),
            "price": row.get("price", "0.00"),
            "qty": row.get("qty", "1"),
            "vat_rate": row.get("vat_rate", "20%"),
            "total_incl_vat": row.get("total_incl_vat", "0.00"),
        })

    return groups


def render_items_table(items: List[Dict[str, str]], vat_rate: str = "20%") -> str:
    """
    Формирует HTML-строку таблицы товаров из списка товаров.
    items: список словарей с ключами product, price, qty, vat_rate, total_incl_vat
    6 колонок: №, Наименование, Кол-во, Цена, НДС%, Сумма с НДС
    """
    rows_html = []
    for idx, item in enumerate(items, 1):
        product = str(item.get("product", "—"))
        price = str(item.get("price", "0.00"))
        qty = str(item.get("qty", "1"))
        item_vat = str(item.get("vat_rate", vat_rate))
        total_incl_vat = str(item.get("total_incl_vat", "0.00"))

        rows_html.append(
            f'<tr>'
            f'<td class="col-num">{idx}</td>'
            f'<td class="col-name">{product}</td>'
            f'<td class="col-qty">{qty}</td>'
            f'<td class="col-price">{price}</td>'
            f'<td class="col-vat">{item_vat}</td>'
            f'<td class="col-total">{total_incl_vat}</td>'
            f'</tr>'
        )

    return "\n".join(rows_html)


def fill_template(html_template: str, invoice_data: Dict[str, Any]) -> str:
    """
    Заполняет HTML-шаблон данными чека.
    invoice_data: словарь с общими полями и списком items.
    """
    result = html_template

    common = invoice_data.get("common", {})
    items = invoice_data.get("items", [])
    vat_rate = common.get("vat_rate", "20%")

    # Шаг 1: Генерируем HTML таблицы товаров
    items_html = render_items_table(items, vat_rate)

    # Шаг 2: Находим и заменяем блок tbody
    tbody_start = result.find('<tbody id="items-body">')
    tbody_end = result.find('</tbody>')

    if tbody_start != -1 and tbody_end != -1:
        tbody_end_plus = result.find('>', tbody_end) + 7  # </tbody>
        new_tbody = f'<tbody id="items-body">\n{items_html}\n            </tbody>'
        result = result[:tbody_start] + new_tbody + result[tbody_end_plus:]

    # Шаг 3: Заполняем остальные поля
    field_mapping = {
        "{{ seller_name }}": common.get("seller_name", ""),
        "{{ seller_inn }}": common.get("seller_inn", ""),
        "{{ seller_address }}": common.get("seller_address", ""),
        "{{ invoice_id }}": common.get("invoice_id", ""),
        "{{ invoice_date }}": common.get("invoice_date", ""),
        "{{ invoice_time }}": common.get("invoice_time", ""),
        "{{ cashier_name }}": common.get("cashier_name", ""),
        "{{ shift_number }}": common.get("shift_number", ""),
        "{{ receipt_type }}": common.get("receipt_type", "приход"),
        "{{ fiscal_document_num }}": common.get("fiscal_document_num", ""),
        "{{ tax_system }}": common.get("tax_system", "ОСН"),
        "{{ fiscal_document }}": common.get("fiscal_document", ""),
        "{{ fiscal_number }}": common.get("fiscal_number", ""),
        "{{ fiscal_doc_version }}": common.get("fiscal_doc_version", "1.2"),
        "{{ kkt_registration_num }}": common.get("kkt_registration_num", ""),
        "{{ fiscal_sign }}": common.get("fiscal_sign", ""),
        "{{ ofd_site }}": common.get("ofd_site", ""),
        "{{ fns_site }}": common.get("fns_site", "www.nalog.gov.ru"),
        "{{ fiscal_form_code }}": common.get("fiscal_form_code", ""),
        "{{ total }}": common.get("total", "0.00"),
        "{{ cash_amount }}": common.get("cash_amount", "0.00"),
        "{{ noncash_amount }}": common.get("noncash_amount", "0.00"),
        "{{ vat_rate_1 }}": common.get("vat_rate_1", "0%"),
        "{{ vat_amount_1 }}": common.get("vat_amount_1", "0.00"),
        "{{ vat_rate_2 }}": common.get("vat_rate_2", "0%"),
        "{{ vat_amount_2 }}": common.get("vat_amount_2", "0.00"),
        "{{ total_pay }}": common.get("total_pay", "0.00"),
        "{{ qr_code_data }}": common.get("qr_code_data", ""),
        "{{ buyer_email }}": common.get("buyer_email", ""),
        "{{ sender_email }}": common.get("sender_email", ""),
        "{{ registration_date }}": common.get("registration_date", ""),
        "{{ site_url }}": common.get("site_url", ""),
    }

    for placeholder, value in field_mapping.items():
        result = result.replace(placeholder, str(value))

    # Шаг 4: Убираем оставшиеся пустые placeholders (на всякий случай)
    import re
    result = re.sub(r'\{\{[^}]+\}\}', '', result)

    return result


def edit_receipt_html(html_content: str) -> str:
    """
    Открывает редактор для ручного редактирования HTML чека перед печатью.
    На Windows используется Notepad, на macOS — open -a TextEdit.
    """
    print("\n  📝  Открыт редактор для редактирования чека...")
    print("  Внесите правки и сохраните файл, затем закройте редактор.")
    print("  Нажмите ENTER после закрытия редактора.")

    tmp_path = OUTPUT_DIR / "receipt_edit.html"
    tmp_path.write_text(html_content, encoding="utf-8")

    try:
        if sys.platform == "win32":
            subprocess.Popen(["notepad.exe", str(tmp_path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "TextEdit", str(tmp_path)])
        else:
            subprocess.Popen(["nano", str(tmp_path)])

        input()  # Ждём, пока пользователь закроет редактор

        edited_content = tmp_path.read_text(encoding="utf-8")
        return edited_content

    except Exception as e:
        print(f"  ⚠  Не удалось открыть редактор: {e}")
        print("  Будет использован исходный HTML без изменений.")
        return html_content


def generate_pdf(html_content: str, output_path: Path) -> bool:
    """
    Генерирует PDF из HTML с помощью WeasyPrint.
    При ошибке (отсутствие GTK на Windows) автоматически переключается на fpdf2.
    """
    # ── Попытка 1: WeasyPrint ──────────────────────────────────────
    try:
        from weasyprint import HTML

        # Определяем путь к шрифту DejaVu Sans
        font_path = _find_dejavu_font()

        # Если шрифт найден, добавляем CSS для принудительного использования
        if font_path:
            font_family = "DejaVu Sans"
            css_override = f"""
            <style>
                @font-face {{
                    font-family: 'DejaVu Sans';
                    src: url('{font_path}');
                }}
                body, .receipt, table, th, td, p, span, div, h2, h3 {{
                    font-family: '{font_family}', Arial, sans-serif !important;
                }}
            </style>
            """
            html_content = html_content.replace("<head>", "<head>" + css_override, 1)

        HTML(string=html_content, encoding="utf-8").write_pdf(str(output_path))
        print("  ✓  PDF сгенерирован через WeasyPrint")
        return True

    except ImportError:
        print("  ℹ  WeasyPrint не установлен. Используем fpdf2...")
    except Exception as e:
        err_msg = str(e).lower()
        # Проверяем, связана ли ошибка с отсутствием GTK/Pango/Cairo
        if any(kw in err_msg for kw in ["gobject", "pango", "cairo", "libglib", "cannot load library"]):
            print(f"  ℹ  GTK библиотеки недоступны ({e}). Используем fpdf2...")
        else:
            print(f"  ✗  Ошибка WeasyPrint: {e}")
            return False

    # ── Попытка 2: fpdf2 (fallback) ────────────────────────────────
    return _generate_pdf_fpdf2(html_content, output_path)


def _generate_pdf_fpdf2(html_content: str, output_path: Path) -> bool:
    """
    Генерирует PDF чека через fpdf2 (fallback для Windows без GTK).
    Использует шрифт Roboto, структура соответствует HTML-шаблону.
    """
    try:
        from fpdf import FPDF

        data = _extract_receipt_data(html_content)

        pdf = FPDF(format=[80, 200])
        pdf.set_auto_page_break(auto=True, margin=8)
        pdf.add_page()

        # Подключаем Roboto
        font_ok = _load_kirilica_font(pdf)
        if not font_ok:
            print("  ⚠  Шрифт Roboto не найден. Используются ASCII-заглушки.")

        def line():
            pdf.line(5, pdf.get_y(), 75, pdf.get_y())
            pdf.ln(1)

        # ── 1. Шапка: продавец ──
        pdf.set_font("Roboto", "B", 9)
        pdf.cell(0, 5, data.get("seller_name", ""), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Roboto", size=7)
        pdf.cell(0, 4, data.get("seller_address", ""), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.cell(0, 4, f"ИНН: {data.get('seller_inn', '')}", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(1)
        line()

        # ── 2. Метаданные ──
        pdf.set_font("Roboto", size=7)
        meta = [
            ("Дата", data.get("invoice_date", "")),
            ("Время", data.get("invoice_time", "")),
            ("Место расчётов", data.get("seller_address", "")),
            ("Смена №", data.get("shift_number", "")),
            ("Чек №", data.get("invoice_id", "")),
            ("Кассир", data.get("cashier_name", "")),
        ]
        for label, value in meta:
            pdf.set_x(5)
            pdf.cell(30, 3, label, align="L")
            pdf.cell(40, 3, value, align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        line()

        # ── 3. Тип чека ──
        pdf.set_font("Roboto", "B", 8)
        pdf.cell(0, 4, "КАССОВЫЙ ЧЕК", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Roboto", size=7)
        pdf.cell(0, 3, data.get("receipt_type", "приход"), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(1)
        line()

        # ── 4. Таблица товаров с шапкой ──
        # Ширины колонок (mm): №5 + Наим32 + Кол8 + Цена9 + НДС6 + Сумма10 = 70
        # "Сумма с НДС" переносится на 2 строки → колонка уже → больше места другим
        col_n = 5; col_nam = 32; col_qty = 8; col_prc = 9; col_vr = 6; col_inv = 10
        x0 = 5   # левая граница таблицы
        lh = 3    # высота строки текста (mm)

        # X-координаты начала каждой колонки (фиксированный grid)
        x_n   = x0                                      # 5
        x_nam = x_n + col_n                             # 10
        x_qty = x_nam + col_nam                         # 42
        x_prc = x_qty + col_qty                         # 50
        x_vr  = x_prc + col_prc                         # 59
        x_inv = x_vr + col_vr                           # 65
        # x_end = x_inv + col_inv = 75

        # ── Шапка таблицы ──
        # Все заголовки в одну строку через cell(), кроме "Сумма с НДС" — multi_cell
        pdf.set_font("Roboto", "B", 6)
        hdr_y = pdf.get_y()
        hdr_h = 6  # высота шапки = 2 строки (для "Сумма\nс НДС")

        # Однострочные заголовки
        pdf.set_xy(x_n, hdr_y)
        pdf.cell(col_n, hdr_h, "№", align="L")
        pdf.cell(col_nam, hdr_h, "Наименование", align="L")
        pdf.cell(col_qty, hdr_h, "Кол-во", align="L")
        pdf.cell(col_prc, hdr_h, "Цена", align="L")
        pdf.cell(col_vr, hdr_h, "НДС%", align="L")

        # "Сумма с НДС" — multi_cell с переносом
        pdf.set_xy(x_inv, hdr_y)
        pdf.multi_cell(col_inv, lh, "Сумма\nс НДС", align="L")

        pdf.set_xy(x0, hdr_y + hdr_h)
        line()

        # ── Тело таблицы ──
        pdf.set_font("Roboto", size=6)
        for item in data.get("items", []):
            row_y = pdf.get_y()

            # Шаг 1: «Наименование» через multi_cell — определяет высоту строки
            pdf.set_xy(x_nam, row_y)
            pdf.multi_cell(col_nam, lh, item.get("product", ""), align="L")
            bottom_y = pdf.get_y()
            row_h = bottom_y - row_y

            # Шаг 2: остальные колонки на той же высоте row_y
            pdf.set_xy(x_n, row_y)
            pdf.cell(col_n, row_h, item.get("num", ""), align="L")

            pdf.set_xy(x_qty, row_y)
            pdf.cell(col_qty, row_h, item.get("qty", ""), align="L")

            pdf.set_xy(x_prc, row_y)
            pdf.cell(col_prc, row_h, item.get("price", ""), align="L")

            pdf.set_xy(x_vr, row_y)
            pdf.cell(col_vr, row_h, item.get("vat_rate", ""), align="L")

            pdf.set_xy(x_inv, row_y)
            pdf.cell(col_inv, row_h, item.get("total_incl_vat", ""), align="L")

            # Шаг 3: следующая строка
            pdf.set_xy(x0, bottom_y)
        pdf.ln(1)
        line()

        # ── 5. Итоги ──
        pdf.set_font("Roboto", size=7)
        totals = [
            ("ИТОГО", data.get("total", "")),
            ("Наличные", data.get("cash_amount", "")),
            ("Безналичные", data.get("noncash_amount", "")),
            (f"НДС {data.get('vat_rate_1', '')}", data.get("vat_amount_1", "")),
            (f"НДС {data.get('vat_rate_2', '')}", data.get("vat_amount_2", "")),
        ]
        for label, value in totals:
            pdf.set_x(5)
            pdf.cell(42, 3, label, align="R")
            pdf.cell(28, 3, value, align="R", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Roboto", "B", 8)
        pdf.line(5, pdf.get_y(), 75, pdf.get_y())
        pdf.set_x(5)
        pdf.cell(42, 4, "К ОПЛАТЕ", align="R")
        pdf.cell(28, 4, data.get("total_pay", ""), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        line()

        # ── 6. Фискальные данные ──
        pdf.set_font("Roboto", size=6)
        fiscal = [
            ("№ авт.", data.get("fiscal_document_num", "")),
            ("СНО", data.get("tax_system", "")),
            ("ФД", data.get("fiscal_document", "")),
            ("ФН", data.get("fiscal_number", "")),
            ("Версия ФФД", data.get("fiscal_doc_version", "")),
            ("РН ККТ", data.get("kkt_registration_num", "")),
            ("ФПД", data.get("fiscal_sign", "")),
            ("Сайт ОФД", data.get("ofd_site", "")),
            ("Сайт ФНС", data.get("fns_site", "")),
            ("Код формы ФД", data.get("fiscal_form_code", "")),
        ]
        for label, value in fiscal:
            pdf.set_x(5)
            pdf.cell(30, 2.5, label, align="L")
            pdf.cell(40, 2.5, value, align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        line()

        # ── 7. QR-код ──
        pdf.set_font("Roboto", size=6)
        pdf.cell(0, 3, data.get("qr_code_data", ""), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.cell(0, 3, "Проверить чек: nalog.ru", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(1)

        # ── 8. Контакты ──
        pdf.cell(0, 2.5, f"Телефон или эл. адрес покупателя: {data.get('buyer_email', '')}", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.cell(0, 2.5, f"Эл. адрес отправителя: {data.get('sender_email', '')}", new_x="LMARGIN", new_y="NEXT", align="C")

        pdf.output(str(output_path))
        print("  ✓  PDF сгенерирован через fpdf2 (fallback, Roboto)")
        return True

    except ImportError:
        print("  ✗  fpdf2 не установлен. Установите: pip install fpdf2")
        return False
    except Exception as e:
        print(f"  ✗  Ошибка fpdf2: {e}")
        return False


def _extract_receipt_data(html: str) -> Dict[str, Any]:
    """Извлекает данные из заполненного HTML-шаблона."""
    import re

    def get_field(pattern: str) -> str:
        m = re.search(pattern, html, re.DOTALL)
        return m.group(1).strip() if m else ""

    def get_items() -> List[Dict[str, str]]:
        """Извлекает строки товаров из tbody таблицы."""
        items = []
        # Находим tbody
        tbody_match = re.search(r'<tbody id="items-body">(.*?)</tbody>', html, re.DOTALL)
        if not tbody_match:
            return items
        tbody = tbody_match.group(1)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody, re.DOTALL)
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if cells:
                clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                if len(clean) >= 6:
                    items.append({
                        "num": clean[0],
                        "product": clean[1],
                        "qty": clean[2],
                        "price": clean[3],
                        "vat_rate": clean[4],
                        "total_incl_vat": clean[5],
                    })
        return items

    data = {
        "seller_name": get_field(r'class="seller-name">(.*?)</div>'),
        "seller_inn": get_field(r'ИНН:\s*(.*?)</div>'),
        "seller_address": get_field(r'class="seller-name">.*?</div>\s*<div>(.*?)</div>'),
        "invoice_date": get_field(r'Дата</td>\s*<td class="value">(.*?)</td>'),
        "invoice_time": get_field(r'Время</td>\s*<td class="value">(.*?)</td>'),
        "cashier_name": get_field(r'Кассир</td>\s*<td class="value">(.*?)</td>'),
        "shift_number": get_field(r'Смена №</td>\s*<td class="value">(.*?)</td>'),
        "invoice_id": get_field(r'Чек №</td>\s*<td class="value">(.*?)</td>'),
        "receipt_type": get_field(r'class="receipt-type">(.*?)</div>'),
        "total": get_field(r'ИТОГО</td>\s*<td class="value">(.*?)</td>'),
        "cash_amount": get_field(r'Наличные</td>\s*<td class="value">(.*?)</td>'),
        "noncash_amount": get_field(r'Безналичные</td>\s*<td class="value">(.*?)</td>'),
        "vat_rate_1": get_field(r'НДС (.*?)</td>\s*<td class="value">.*?</td>\s*</tr>\s*<tr>\s*<td class="label">НДС'),
        "vat_amount_1": get_field(r'НДС.*?</td>\s*<td class="value">(.*?)</td>\s*</tr>\s*<tr>\s*<td class="label">НДС'),
        "vat_rate_2": get_field(r'К ОПЛАТЕ.*?НДС (.*?)</td>'),
        "vat_amount_2": "",
        "total_pay": get_field(r'К ОПЛАТЕ</td>\s*<td class="value">(.*?)</td>'),
        "fiscal_document_num": get_field(r'№ авт\.</td>\s*<td class="value">(.*?)</td>'),
        "tax_system": get_field(r'СНО</td>\s*<td class="value">(.*?)</td>'),
        "fiscal_document": get_field(r'<td class="label">ФД</td>\s*<td class="value">(.*?)</td>'),
        "fiscal_number": get_field(r'<td class="label">ФН</td>\s*<td class="value">(.*?)</td>'),
        "fiscal_doc_version": get_field(r'Версия ФФД</td>\s*<td class="value">(.*?)</td>'),
        "kkt_registration_num": get_field(r'РН ККТ</td>\s*<td class="value">(.*?)</td>'),
        "fiscal_sign": get_field(r'<td class="label">ФПД</td>\s*<td class="value">(.*?)</td>'),
        "ofd_site": get_field(r'Сайт ОФД</td>\s*<td class="value">(.*?)</td>'),
        "fns_site": get_field(r'Сайт ФНС</td>\s*<td class="value">(.*?)</td>'),
        "fiscal_form_code": get_field(r'Код формы ФД</td>\s*<td class="value">(.*?)</td>'),
        "qr_code_data": get_field(r'class="qr-block">\s*<div>(.*?)</div>'),
        "buyer_email": get_field(r'покупателя:\s*(.*?)</div>'),
        "sender_email": get_field(r'отправителя:\s*(.*?)</div>'),
        "items": get_items(),
    }

    # Достаём vat_rate_1, vat_amount_1, vat_rate_2, vat_amount_2 более надёжно
    vat_rows = re.findall(r'НДС (.*?)</td>\s*<td class="value">(.*?)</td>', html)
    if len(vat_rows) >= 1:
        data["vat_rate_1"] = vat_rows[0][0]
        data["vat_amount_1"] = vat_rows[0][1]
    if len(vat_rows) >= 2:
        data["vat_rate_2"] = vat_rows[1][0]
        data["vat_amount_2"] = vat_rows[1][1]

    return data


def _load_kirilica_font(pdf: "FPDF") -> bool:
    """Подключает шрифт Roboto (скачанный в templates/) или fallback на Arial."""
    # 1. Ищем Roboto в templates/
    roboto_regular = TEMPLATES_DIR / "Roboto-Regular.ttf"
    roboto_bold = TEMPLATES_DIR / "Roboto-Bold.ttf"

    if roboto_regular.exists():
        try:
            pdf.add_font("Roboto", "", str(roboto_regular))
            if roboto_bold.exists():
                pdf.add_font("Roboto", "B", str(roboto_bold))
            else:
                pdf.add_font("Roboto", "B", str(roboto_regular))
            pdf.set_font("Roboto")
            return True
        except Exception:
            pass

    # 2. Fallback: Arial из системы
    font_candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    ]

    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                pdf.add_font("Arial", "", font_path)
                bd_path = font_path.replace(".ttf", "bd.ttf") if "bd" not in font_path else font_path
                if os.path.exists(bd_path):
                    pdf.add_font("Arial", "B", bd_path)
                pdf.set_font("Arial")
                return True
            except Exception:
                continue

    return False


def _find_dejavu_font() -> Optional[str]:
    """Ищет шрифт DejaVu Sans на системе."""
    possible_names = ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
    possible_paths = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        # macOS
        "/System/Library/Fonts/DejaVuSans.ttf",
        os.path.expanduser("~/.fonts/DejaVuSans.ttf"),
        os.path.expanduser("~/.local/share/fonts/DejaVuSans.ttf"),
        # Windows (через пакет weasyprint или встроенный)
        "C:\\Windows\\Fonts\\DejaVuSans.ttf",
        "C:\\Program Files\\Python311\\Lib\\site-packages\\weasyprint\\fonts\\DejaVuSans.ttf",
    ]

    for pp in possible_paths:
        if os.path.exists(pp):
            return pp

    # Пробуем найти через glob
    import glob as glob_mod
    for search_path in [
        "/usr/share/fonts/**/DejaVuSans.ttf",
        os.path.expanduser("~/.fonts/**/*.ttf"),
        "C:\\Windows\\Fonts\\DejaVu*.ttf",
    ]:
        matches = glob_mod.glob(search_path, recursive=True)
        if matches:
            return matches[0]

    return None


def open_pdf(filepath: Path) -> bool:
    """Открывает PDF в системной программе просмотра."""
    try:
        if sys.platform == "win32":
            os.startfile(str(filepath))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
        return True
    except Exception as e:
        print(f"  ⚠  Не удалось открыть PDF: {e}")
        print(f"  Файл сохранён: {filepath}")
        return False


# ---------------------------------------------------------------------------
# Основной цикл (main loop) с защитой от разрывов
# ---------------------------------------------------------------------------


def main():
    """Главная функция — цикл запрос-выдача с полной обработкой ошибок."""
    # ── Нулевой шаг: проверка зависимостей ──
    print_banner()
    print("\n  ─── Шаг 0: Проверка окружения ───")
    env_ok = run_environment_check()
    if not env_ok:
        print("\n  ⚠  Не все зависимости установлены. Программа может работать некорректно.")
        print("  ℹ  Будет использован fpdf2 (fallback) для генерации PDF.\n")

    print("\n  ─── Шаг 1: Загрузка файлов данных ───")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data_files = load_all_data_files()

    if not data_files:
        print("\n✗  Ошибка: не найдено ни одного файла данных в директории /data")
        print("  Создайте CSV или JSON файл с данными и положите в /data")
        sys.exit(1)

    # ── Шаг 2: Выбор файла данных ──────────────────────────────────
    print("\n[2/6] Выберите файл данных:")
    data_menu_items = [f"{fp.name} ({ftype}, {len(data)} записей)" for fp, ftype, data in data_files]
    data_choice = print_menu(data_menu_items, "Файлы данных")

    if data_choice >= len(data_files):
        print("\n  👋  До свидания!")
        return

    selected_data_path, selected_data_type, selected_data = data_files[data_choice]
    print(f"\n  ✓  Выбран: {selected_data_path.name} ({selected_data_type}, {len(selected_data)} записей)")

    # ── Шаг 3: Загрузка шаблонов ───────────────────────────────────
    print("\n[3/6] Сканирование директории шаблонов...")
    templates = load_all_templates()

    if not templates:
        print("\n✗  Ошибка: не найдено ни одного HTML-шаблона в директории /templates")
        print("  Создайте HTML-файл с placeholders и положите в /templates")
        sys.exit(1)

    # ── Шаг 4: Выбор шаблона ───────────────────────────────────────
    print("\n[4/6] Выберите HTML-шаблон:")
    template_menu_items = [name for _, name in templates]
    template_choice = print_menu(template_menu_items, "HTML-шаблоны")

    if template_choice >= len(templates):
        print("\n  👋  До свидания!")
        return

    selected_template_path, selected_template_name = templates[template_choice]

    # ── Шаг 5: Валидация шаблона ───────────────────────────────────
    print(f"\n[5/6] Проверка шаблона '{selected_template_name}'...")
    try:
        html_template = selected_template_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"\n✗  Ошибка чтения шаблона: {e}")
        sys.exit(1)

    is_valid, missing = validate_html_placeholders(html_template)

    if not is_valid:
        print(f"\n  ⚠  Шаблон не содержит обязательных placeholders:")
        for ph in missing:
            print(f"    — {ph}")
        print(f"\n  Требуется минимум: {' | '.join(REQUIRED_PLACEHOLDERS)}")

        while True:
            choice = input("  Продолжить с этим шаблоном? (y/n): ").strip().lower()
            if choice in ("y", "yes", "да"):
                break
            elif choice in ("n", "no", "нет"):
                print("\n  💡 Рекомендация:")
                print("     1. Добавьте отсутствующие placeholders в HTML-шаблон")
                print("     2. Скопируйте тестовый шаблон:")
                print(f"        copy templates\receipt_template.html {selected_template_name}")
                print("     3. Или используйте другой шаблон из списка")
                continue
            else:
                print("  Введите 'y' или 'n'")
        print("  ⏭  Продолжаем с текущим шаблоном...")

    print("  ✓  Шаблон проверен. Placeholders обнаружены.")

    # ── Шаг 6: Выбор invoice ID ────────────────────────────────────
    print(f"\n[6/6] Выберите invoice ID из '{selected_data_path.name}':")

    # Подготовка уникальных invoice ID
    if selected_data_type == "CSV":
        invoice_groups = group_csv_items_by_invoice(selected_data)
        unique_inv_ids = list(invoice_groups.keys())
    else:  # JSON
        # JSON: items вложены в объект, остальные поля — наверху
        invoice_groups = {}
        for item in selected_data:
            inv_id = item.get("invoice_id", "UNKNOWN")
            items_list = item.get("items", [])
            # Убираем items из common
            common_fields = {k: v for k, v in item.items() if k != "items"}
            invoice_groups[inv_id] = {"common": common_fields, "items": items_list}
        unique_inv_ids = list(invoice_groups.keys())

    print("-" * 50)
    for i, inv_id in enumerate(unique_inv_ids):
        group_data = invoice_groups[inv_id]
        items = group_data.get("items", []) if isinstance(group_data, dict) else []
        common = group_data.get("common", {}) if isinstance(group_data, dict) else {}
        seller = common.get("seller_name", "N/A") if common else "N/A"
        date = common.get("invoice_date", "N/A") if common else "N/A"
        total = common.get("total_pay", common.get("total", "N/A")) if common else "N/A"
        n_items = len(items) if isinstance(items, list) else 0
        print(f"  {i + 1}. {inv_id}  |  {seller}  |  {date}  |  {n_items} тов.  |  {total} ₽")
    print(f"  {len(unique_inv_ids) + 1}. ← Назад / Выход")
    print("-" * 50)

    while True:
        try:
            inv_choice = input("  Выбор invoice ID (номер): ").strip()
            inv_num = int(inv_choice)
            if 1 <= inv_num <= len(unique_inv_ids) + 1:
                break
            print("  ⚠  Введите число от 1 до", len(unique_inv_ids) + 1)
        except ValueError:
            print("  ⚠  Введите корректный номер.")

    if inv_num > len(unique_inv_ids):
        print("\n  👋  До свидания!")
        return

    selected_inv_id = unique_inv_ids[inv_num - 1]
    invoice_data = invoice_groups[selected_inv_id]
    print(f"\n  ✓  Выбран: {selected_inv_id} ({len(invoice_data.get('items', []))} товаров)")

    # ── Генерация HTML ─────────────────────────────────────────────
    print("\n  🔄  Генерация HTML чека...")
    generated_html = fill_template(html_template, invoice_data)

    # ── Редактирование чека ────────────────────────────────────────
    while True:
        print("\n  Что сделать с чеком?")
        edit_choice = input("  1) Отредактировать HTML  |  2) Печать PDF  |  3) Выход  →  ")

        if edit_choice.strip() == "1":
            generated_html = edit_receipt_html(generated_html)
            print("  ✓  HTML отредактирован.")
        elif edit_choice.strip() == "2":
            break
        elif edit_choice.strip() == "3":
            print("\n  👋  До свидания!")
            return
        else:
            print("  ⚠  Введите 1, 2 или 3.")

    # ── Генерация PDF ──────────────────────────────────────────────
    print("\n  📄  Генерация PDF...")
    output_filename = f"receipt_{selected_inv_id}.pdf"
    output_path = OUTPUT_DIR / output_filename

    success = generate_pdf(generated_html, output_path)

    if not success:
        print("\n✗  Не удалось сгенерировать PDF!")
        sys.exit(1)

    print(f"\n  ✓  PDF сохранён: {output_path}")
    print(f"  📁  Директория: {OUTPUT_DIR}")

    # ── Открытие PDF ───────────────────────────────────────────────
    print("\n  🖨  Открытие PDF в системной программе...")
    open_pdf(output_path)

    print("\n" + "=" * 60)
    print("  ✅  Готово! Проверьте сгенерированный чек.")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Обработчик критических ошибок
# ---------------------------------------------------------------------------


def handle_critical_error(error: Exception, context: str = "") -> None:
    """
    Fallback-обработчик критических ошибок.
    Логирует ошибку и предлагает варианты действий.
    """
    print(f"\n{'!' * 60}")
    print(f"  КРИТИЧЕСКАЯ ОШИБКА в: {context}")
    print(f"  Сообщение: {error}")
    print(f"{'!' * 60}")
    print("\n  Варианты:")
    print("    1. Повторить попытку")
    print("    2. Использовать данные по умолчанию")
    print("    3. Выйти из программы")

    while True:
        try:
            choice = input("  Ваш выбор (1/2/3): ").strip()
            if choice == "1":
                raise error  # Повторный вызов
            elif choice == "2":
                print("  ⚠  Использование данных по умолчанию...")
                return
            elif choice == "3":
                sys.exit(1)
            else:
                print("  Введите 1, 2 или 3")
        except EOFError:
            print("  ⚠  Pipe-ввод завершён. Выход.")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n  👋  Прервано пользователем.")
            sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  ⚠  Прервано пользователем (Ctrl+C).")
        print("  👋  До свидания!\n")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        handle_critical_error(e, "main()")
        sys.exit(1)
