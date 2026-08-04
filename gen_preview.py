#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генерирует PDF-предпросмотр структуры чека с плейсхолдерами."""

from fpdf import FPDF
from pathlib import Path

pdf = FPDF(format=[80, 200])
pdf.set_auto_page_break(auto=True, margin=8)
pdf.add_page()

arial = r"C:\Windows\Fonts\arial.ttf"
arialb = r"C:\Windows\Fonts\arialbd.ttf"
pdf.add_font("Arial", "", arial)
pdf.add_font("Arial", "B", arialb)

def line():
    pdf.line(5, pdf.get_y(), 75, pdf.get_y())
    pdf.ln(1)

# ── 1. Шапка: продавец ──
pdf.set_font("Arial", "B", 9)
pdf.cell(0, 5, "[Название компании]", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.set_font("Arial", size=7)
pdf.cell(0, 4, "[Адрес компании]", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.cell(0, 4, "ИНН: [ИНН компании]", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.ln(1)
line()

# ── 2. Метаданные ──
pdf.set_font("Arial", size=7)
meta = [
    ("Дата", "[Дата чека]"),
    ("Время", "[Время чека]"),
    ("Место расчётов", "[Место расчётов]"),
    ("Смена №", "[Номер смены]"),
    ("Чек №", "[Номер чека]"),
    ("Кассир", "[ФИО кассира]"),
]
for label, value in meta:
    pdf.set_x(5)
    pdf.cell(30, 3, label, align="L")
    pdf.cell(40, 3, value, align="R", new_x="LMARGIN", new_y="NEXT")
pdf.ln(1)
line()

# ── 3. Тип чека ──
pdf.set_font("Arial", "B", 8)
pdf.cell(0, 4, "КАССОВЫЙ ЧЕК", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.set_font("Arial", size=7)
pdf.cell(0, 3, "[Тип операции: приход]", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.ln(1)
line()

# ── 4. Таблица товаров с шапкой ──
# Шрифт 6px, 6 колонок в 70mm (x=5 до x=75)
# Расклад: №5 + Наим25 + Кол8 + Цена12 + НДС%8 + ΣсНДС12 = 70
col_n   = 5   # №
col_nam = 25  # Наименование
col_qty = 8   # Кол-во
col_prc = 12  # Цена
col_vr  = 8   # НДС%
col_inv = 12  # Σ с НДС

pdf.set_font("Arial", "B", 6)
pdf.set_x(5)
pdf.cell(col_n,  4, "№",          align="C")
pdf.cell(col_nam,4, "Наименование", align="L")
pdf.cell(col_qty,4, "Кол-во",     align="C")
pdf.cell(col_prc,4, "Цена",       align="R")
pdf.cell(col_vr, 4, "НДС%",       align="R")
pdf.cell(col_inv,4, "Σ с НДС",    align="R", new_x="LMARGIN", new_y="NEXT")
line()

# 3 строки-примера — все числовые данные заменены на [***]
pdf.set_font("Arial", size=6)
rows = [
    ("1", "[Наименование позиции]", "[***]", "[***]", "[***]", "[***]"),
    ("2", "[Наименование позиции]", "[***]", "[***]", "[***]", "[***]"),
    ("3", "[Наименование позиции]", "[***]", "[***]", "[***]", "[***]"),
]
for r in rows:
    pdf.set_x(5)
    pdf.cell(col_n,  3, r[0], align="C")
    pdf.cell(col_nam,3, r[1], align="L")
    pdf.cell(col_qty,3, r[2], align="C")
    pdf.cell(col_prc,3, r[3], align="R")
    pdf.cell(col_vr, 3, r[4], align="R")
    pdf.cell(col_inv,3, r[5], align="R", new_x="LMARGIN", new_y="NEXT")
pdf.ln(1)
line()

# ── 5. Итоги ──
pdf.set_font("Arial", size=7)
totals = [
    ("ИТОГО", "[***]"),
    ("Наличные", "[***]"),
    ("Безналичные", "[***]"),
    ("НДС [ставка 1]", "[***]"),
    ("НДС [ставка 2]", "[***]"),
]
for label, value in totals:
    pdf.set_x(5)
    pdf.cell(42, 3, label, align="R")
    pdf.cell(28, 3, value, align="R", new_x="LMARGIN", new_y="NEXT")

pdf.set_font("Arial", "B", 8)
pdf.line(5, pdf.get_y(), 75, pdf.get_y())
pdf.set_x(5)
pdf.cell(42, 4, "К ОПЛАТЕ", align="R")
pdf.cell(28, 4, "[***]", align="R", new_x="LMARGIN", new_y="NEXT")
pdf.ln(1)
line()

# ── 6. Фискальные данные ──
pdf.set_font("Arial", size=6)
fiscal = [
    ("№ авт.", "[Номер документа]"),
    ("СНО", "[Система налогообложения]"),
    ("ФД", "[Номер ФД]"),
    ("ФН", "[Номер ФН]"),
    ("Версия ФФД", "[Версия ФФД]"),
    ("РН ККТ", "[Рег. номер ККТ]"),
    ("ФПД", "[Фискальный признак]"),
    ("Сайт ОФД", "[Сайт ОФД]"),
    ("Сайт ФНС", "[Сайт ФНС]"),
    ("Код формы ФД", "[Код формы ФД]"),
]
for label, value in fiscal:
    pdf.set_x(5)
    pdf.cell(30, 2.5, label, align="L")
    pdf.cell(40, 2.5, value, align="R", new_x="LMARGIN", new_y="NEXT")
pdf.ln(1)
line()

# ── 7. QR-код ──
pdf.set_font("Arial", size=6)
pdf.cell(0, 3, "[Данные QR-кода]", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.cell(0, 3, "Проверить чек: nalog.ru", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.ln(1)

# ── 8. Контакты ──
pdf.cell(0, 2.5, "Телефон или эл. адрес покупателя: [Email покупателя]", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.cell(0, 2.5, "Эл. адрес отправителя: [Email отправителя]", new_x="LMARGIN", new_y="NEXT", align="C")

pdf.output("output/structure_preview_v3.pdf")
print("OK: output/structure_preview_v3.pdf")
