"""Сборка короткого видео-демонстрации из скриншотов интерфейса.

Скрипт рисует слайды 1280x720 (заголовок, подписи, скриншот) и склеивает их
через ffmpeg с плавными переходами. Требуется установленный ffmpeg.

Пример:
    python scripts/make_demo_video.py --ffmpeg C:/ffmpeg/bin/ffmpeg.exe
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

WIDTH, HEIGHT = 1280, 720
BG_TOP = (11, 17, 32)
BG_BOTTOM = (30, 27, 75)
ACCENT = (129, 140, 248)
TEXT = (229, 231, 235)
MUTED = (148, 163, 184)
PANEL = (17, 24, 39)

FONT_DIR = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / name
    if not path.is_file():
        path = FONT_DIR / "arial.ttf"
    return ImageFont.truetype(str(path), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, face, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=face) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_TOP)
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        color = tuple(
            int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * ratio) for i in range(3)
        )
        draw.line([(0, y), (WIDTH, y)], fill=color)
    draw.ellipse((820, -220, 1500, 460), fill=(99, 102, 241, 26))
    draw.ellipse((-260, 420, 380, 1000), fill=(14, 165, 233, 18))
    return image


def brand(image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((64, 40, 104, 80), radius=12, fill=(79, 70, 229))
    for index, height in enumerate((16, 26, 12, 22)):
        x = 73 + index * 8
        draw.rectangle((x, 74 - height, x + 4, 74), fill=(255, 255, 255))
    draw.text((116, 47), "DataScope", font=font("segoeuib.ttf", 20), fill=TEXT)
    draw.text(
        (116, 68),
        "сервис обработки и визуализации данных",
        font=font("segoeui.ttf", 11),
        fill=MUTED,
    )


def footer(image: Image.Image, draw: ImageDraw.ImageDraw, index: int, total: int) -> None:
    draw.line((64, 678, WIDTH - 64, 678), fill=(255, 255, 255, 28), width=1)
    draw.text((64, 690), "DataScope · демонстрация", font=font("segoeui.ttf", 11), fill=MUTED)
    counter = f"{index:02d} / {total:02d}"
    draw.text((WIDTH - 104, 690), counter, font=font("segoeui.ttf", 11), fill=MUTED)
    progress = (index / total) * (WIDTH - 128)
    draw.rectangle((64, 706, 64 + progress, 709), fill=ACCENT)


def rounded_image(source: Path, box: tuple[int, int, int, int]) -> Image.Image:
    width = box[2] - box[0]
    height = box[3] - box[1]
    picture = Image.open(source).convert("RGB")
    picture = ImageOps.contain(picture, (width, height))
    mask = Image.new("L", picture.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, picture.width, picture.height), radius=16, fill=255)

    shadow = Image.new("RGBA", (width + 40, height + 40), (0, 0, 0, 0))
    shadow.paste(Image.new("RGBA", picture.size, (0, 0, 0, 170)), ((width + 40 - picture.width) // 2, (height + 40 - picture.height) // 2))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(shadow.crop((20, 20, width + 20, height + 20)), (0, 0))
    canvas.paste(picture, ((width - picture.width) // 2, (height - picture.height) // 2), mask)
    return canvas


def content_slide(
    screenshot: Path,
    kicker: str,
    title: str,
    description: str,
    bullets: list[str],
) -> Image.Image:
    image = background()
    draw = ImageDraw.Draw(image, "RGBA")
    brand(image, draw)

    left = 64
    text_width = 330
    draw.text((left, 132), kicker, font=font("segoeuib.ttf", 12), fill=ACCENT)
    y = 156
    for line in wrap(draw, title, font("segoeuib.ttf", 34), text_width):
        draw.text((left, y), line, font=font("segoeuib.ttf", 34), fill=TEXT)
        y += 42
    y += 10
    for line in wrap(draw, description, font("segoeui.ttf", 16), text_width):
        draw.text((left, y), line, font=font("segoeui.ttf", 16), fill=MUTED)
        y += 24
    y += 18
    for bullet in bullets:
        draw.ellipse((left, y + 6, left + 6, y + 12), fill=ACCENT)
        for line in wrap(draw, bullet, font("segoeui.ttf", 13), text_width - 22):
            draw.text((left + 18, y), line, font=font("segoeui.ttf", 13), fill=TEXT)
            y += 20
        y += 10

    picture = rounded_image(screenshot, (430, 108, 1216, 652))
    image.paste(picture, (430, 108), picture)
    return image


def title_slide(total: int) -> Image.Image:
    image = background()
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((64, 150, 128, 214), radius=16, fill=(79, 70, 229))
    for index, height in enumerate((28, 46, 22, 38)):
        x = 80 + index * 14
        draw.rectangle((x, 198 - height, x + 8, 198), fill=(255, 255, 255))
    draw.text((64, 246), "DataScope", font=font("segoeuib.ttf", 64), fill=TEXT)
    draw.text(
        (68, 326),
        "Сервис обработки и визуализации данных",
        font=font("segoeui.ttf", 26),
        fill=MUTED,
    )
    draw.text(
        (68, 368),
        "Технические характеристики видео и телеметрия трекинга — в одном дашборде",
        font=font("segoeui.ttf", 16),
        fill=(203, 213, 225),
    )

    chips = ["FastAPI", "Plotly", "SQLite", "26 графиков", "78 тестов"]
    x = 68
    for chip in chips:
        width = int(draw.textlength(chip, font=font("segoeuib.ttf", 13))) + 28
        draw.rounded_rectangle((x, 430, x + width, 466), radius=18, fill=(30, 27, 75), outline=(99, 102, 241))
        draw.text((x + 14, 439), chip, font=font("segoeuib.ttf", 13), fill=TEXT)
        x += width + 10

    draw.text(
        (68, 540),
        "python -m src.main  →  http://127.0.0.1:8000",
        font=font("segoeui.ttf", 15),
        fill=ACCENT,
    )
    footer(image, draw, 1, total)
    return image


def final_slide(total: int) -> Image.Image:
    image = background()
    draw = ImageDraw.Draw(image, "RGBA")
    brand(image, draw)
    draw.text((64, 170), "ИТОГИ", font=font("segoeuib.ttf", 12), fill=ACCENT)
    draw.text((64, 198), "Что внутри", font=font("segoeuib.ttf", 44), fill=TEXT)

    stats = [
        ("26", "интерактивных графиков"),
        ("8", "KPI-карточек"),
        ("78", "автотестов pytest"),
        ("12", "эндпоинтов REST API"),
    ]
    positions = [(64, 330), (356, 330), (64, 470), (356, 470)]
    for (value, label), (x, y) in zip(stats, positions, strict=True):
        draw.rounded_rectangle((x, y, x + 260, y + 110), radius=16, fill=PANEL, outline=(55, 65, 81))
        draw.text((x + 22, y + 18), value, font=font("segoeuib.ttf", 40), fill=ACCENT)
        draw.text((x + 22, y + 74), label, font=font("segoeui.ttf", 14), fill=MUTED)

    draw.text((700, 340), "Нормализация «грязных» Excel-отчётов", font=font("segoeuib.ttf", 18), fill=TEXT)
    for index, line in enumerate(
        [
            "Потоковый парсер и SQL-агрегации",
            "График по каждой метрике листа",
            "CSV / XLSX экспорт выборки",
            "Тёмная тема и офлайн-Plotly",
        ]
    ):
        draw.ellipse((700, 388 + index * 34, 706, 394 + index * 34), fill=ACCENT)
        draw.text((718, 382 + index * 34), line, font=font("segoeui.ttf", 15), fill=MUTED)

    footer(image, draw, total, total)
    return image


def build_slides(screenshots: Path) -> list[Image.Image]:
    slides = [
        title_slide(8),
        content_slide(
            screenshots / "dashboard.png",
            "ДАШБОРД",
            "Учёт по месяцам",
            "26 интерактивных графиков: по одному на каждую метрику листа.",
            ["Столбцы — среднее за период", "Усы — минимум и максимум", "Линия — количество эпизодов"],
        ),
        content_slide(
            screenshots / "dashboard-day.png",
            "ДЕТАЛИЗАЦИЯ",
            "По дням и по всему объёму",
            "Переключение день / месяц / весь объём пересчитывает все карточки.",
            ["Фильтры по периоду и отчёту", "Среднее, сумма, минимум, максимум", "8 KPI-карточек"],
        ),
        content_slide(
            screenshots / "trackers.png",
            "ЛИСТ «ТРЕКЕРЫ»",
            "Телеметрия трекинга",
            "12 графиков: частота в начале, середине и конце, равномерность и пропуски.",
            ["Битые файлы не занижают среднее", "Стек по категориям", "Гистограммы для всего объёма"],
        ),
        content_slide(
            screenshots / "dark.png",
            "ОФОРМЛЕНИЕ",
            "Светлая и тёмная тема",
            "Plotly-фигуры перестраиваются под тему, выбор сохраняется в браузере.",
            ["Адаптивная сетка карточек", "Plotly работает офлайн", "Ссылка на состояние дашборда"],
        ),
        content_slide(
            screenshots / "table.png",
            "ДАННЫЕ",
            "Таблица и экспорт",
            "Поиск, сортировка по любой колонке, пагинация и выгрузка выборки.",
            ["CSV и Excel", "Поиск по кириллице", "19 колонок отчёта"],
        ),
        content_slide(
            screenshots / "reports.png",
            "ОТЧЁТЫ",
            "Управление загрузками",
            "Каждый отчёт хранится отдельно, дубликаты определяются по SHA-256.",
            ["Загрузка drag-and-drop", "Скачивание исходника", "Удаление вместе со строками"],
        ),
        final_slide(8),
    ]
    return slides


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка docs/demo.mp4")
    parser.add_argument("--screenshots", default="docs/screenshots", type=Path)
    parser.add_argument("--output", default="docs/demo.mp4", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg", help="путь к ffmpeg")
    parser.add_argument("--seconds", default=5.4, type=float, help="длительность слайда")
    args = parser.parse_args()

    slides = build_slides(args.screenshots)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        frames = []
        for index, slide in enumerate(slides):
            path = tmp_path / f"frame_{index:02d}.png"
            slide.save(path)
            frames.append(path)

        duration = args.seconds
        transition = 0.4
        inputs: list[str] = []
        for frame in frames:
            inputs += ["-loop", "1", "-t", str(duration), "-i", str(frame)]

        filters = []
        for index in range(len(frames)):
            filters.append(f"[{index}:v]scale={WIDTH}:{HEIGHT},setsar=1,format=yuv420p[v{index}]")
        current = "v0"
        for index in range(1, len(frames)):
            offset = round(index * (duration - transition), 3)
            output = f"x{index}"
            filters.append(
                f"[{current}][v{index}]xfade=transition=fade:duration={transition}:offset={offset}[{output}]"
            )
            current = output

        command = [
            args.ffmpeg,
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{current}]",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "22",
            "-movflags",
            "+faststart",
            str(args.output),
        ]
        print("ffmpeg:", " ".join(command[:6]), "...")
        subprocess.run(command, check=True)

    size = args.output.stat().st_size
    print(f"Готово: {args.output} ({size / 1024 / 1024:.1f} МБ)")


if __name__ == "__main__":
    main()
