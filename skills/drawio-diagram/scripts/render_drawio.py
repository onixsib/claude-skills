#!/usr/bin/env python3
"""
Рендерит файл .drawio в PNG и режет картинку на плитки для проверки глазами.

Зачем: схема проверяется только по рендеру — наезды подписей и обрезанный текст в XML
не видны. Большая схема целиком при просмотре уменьшается, и мелкий текст на ней не
прочитать, поэтому рядом с полной картинкой делаются плитки в натуральную величину.

Запуск:
    python3 render_drawio.py scheme.drawio
    python3 render_drawio.py scheme.drawio --output out.png --scale 1.5 --tiles-dir /tmp/tiles

Что нужно: приложение draw.io с командной строкой (команда drawio или draw.io).
Для плиток — Pillow; без него рендер делается, плитки пропускаются.

Побочные эффекты: пишет PNG (по умолчанию рядом с исходником, с тем же именем) и плитки
(по умолчанию в новый каталог в системном временном каталоге, путь печатается; свой каталог —
--tiles-dir). Существующий PNG перезаписывается. Плитки нужны только для просмотра: после
проверки их можно удалить.

Коды возврата: 0 — готово; 2 — нет draw.io; 3 — экспорт не удался.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Плитка такого размера при просмотре не уменьшается, текст остаётся читаемым
DEFAULT_TILE_SIZE = 1500
# Перекрытие плиток: блок на стыке целиком попадает хотя бы в одну из них.
# Блок шире перекрытия на стыке всё равно разрежется — такой смотри с --tile-size побольше.
TILE_OVERLAP = 300

# draw.io — приложение на Electron и сыплет в stderr сообщениями графической подсистемы.
# На результат они не влияют, а настоящую ошибку в них легко пропустить.
NOISE_MARKERS = ("wayland", "dbus", "gpu", "gtk", "libva", "fontconfig", "vaapi", "viz_main")


def find_drawio():
    for name in ("drawio", "draw.io"):
        path = shutil.which(name)
        if path:
            return path
    return None


def export_png(drawio, source, output, scale, border):
    command = [drawio, "--export", "--format", "png", "--scale", str(scale), "--border", str(border),
               "--output", str(output), str(source), "--no-sandbox"]
    # Без дисплея Electron не стартует; xvfb-run даёт ему виртуальный
    has_display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if not has_display and shutil.which("xvfb-run"):
        command = ["xvfb-run", "-a"] + command
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    real_errors = [line for line in result.stderr.splitlines()
                   if line.strip() and not any(marker in line.lower() for marker in NOISE_MARKERS)]
    if result.returncode != 0 or not output.exists():
        print("Экспорт не удался. Вывод draw.io:", file=sys.stderr)
        print("\n".join(real_errors) or result.stderr, file=sys.stderr)
        if not has_display and not shutil.which("xvfb-run"):
            print("Дисплея нет и xvfb-run не установлен: поставь xvfb или запусти там, где есть графическая сессия.",
                  file=sys.stderr)
        return False
    return True


def make_tiles(image_path, tiles_dir, tile_size):
    try:
        from PIL import Image
    except ImportError:
        print("Pillow не установлен — плитки не сделаны. Смотри PNG целиком или поставь: pip install pillow")
        return []
    image = Image.open(image_path)
    width, height = image.size
    print(f"Размер PNG: {width} x {height}")
    if width <= tile_size and height <= tile_size:
        print("Картинка помещается в одну плитку — смотри PNG целиком.")
        return []
    if tiles_dir is None:
        tiles_dir = Path(tempfile.mkdtemp(prefix="drawio-tiles-"))
    tiles_dir.mkdir(parents=True, exist_ok=True)
    tiles = []
    for row, top in enumerate(tile_offsets(height, tile_size), start=1):
        for column, left in enumerate(tile_offsets(width, tile_size), start=1):
            box = (left, top, min(left + tile_size, width), min(top + tile_size, height))
            tile_path = tiles_dir / f"{image_path.stem}.r{row}c{column}.png"
            image.crop(box).save(tile_path)
            tiles.append(tile_path)
    return tiles


def tile_offsets(length, tile_size):
    """Начала плиток вдоль одной стороны картинки.

    Плитки распределяются равномерно: вместо полных плиток и узкого огрызка в конце
    получаются одинаковые плитки с перекрытием не меньше TILE_OVERLAP.
    """
    if length <= tile_size:
        return [0]
    step = tile_size - TILE_OVERLAP
    count = -(-(length - TILE_OVERLAP) // step)   # деление с округлением вверх
    last_start = length - tile_size
    return [round(index * last_start / (count - 1)) for index in range(count)]


def main():
    parser = argparse.ArgumentParser(description="Рендер .drawio в PNG и плитки для проверки")
    parser.add_argument("source", type=Path, help="файл .drawio")
    parser.add_argument("--output", type=Path, help="PNG; по умолчанию рядом с исходником")
    parser.add_argument("--scale", type=float, default=1.5, help="масштаб экспорта (по умолчанию 1.5)")
    parser.add_argument("--border", type=int, default=10, help="поле вокруг схемы в пикселях")
    parser.add_argument("--tiles-dir", type=Path, help="каталог для плиток; по умолчанию временный")
    parser.add_argument("--tile-size", type=int, default=DEFAULT_TILE_SIZE, help="сторона плитки в пикселях")
    parser.add_argument("--no-tiles", action="store_true", help="не резать на плитки")
    arguments = parser.parse_args()

    if not arguments.source.exists():
        sys.exit(f"Нет файла: {arguments.source}")
    drawio = find_drawio()
    if not drawio:
        print("Не найдена команда drawio (draw.io). Файл .drawio остаётся как есть, но рендер не проверен.\n"
              "Установи draw.io Desktop: https://github.com/jgraph/drawio-desktop/releases", file=sys.stderr)
        return 2

    output = arguments.output or arguments.source.with_suffix(".png")
    if not export_png(drawio, arguments.source, output, arguments.scale, arguments.border):
        return 3
    print(f"PNG: {output}")

    if not arguments.no_tiles:
        tiles = make_tiles(output, arguments.tiles_dir, arguments.tile_size)
        if tiles:
            print(f"Плитки для проверки ({len(tiles)} шт.), смотреть каждую:")
            for tile in tiles:
                print(f"  {tile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
