#!/usr/bin/env python3
"""
Библиотека для сборки схем draw.io из Python.

Зачем: большую схему руками в XML не выверить, а автораскладка draw.io на плотных схемах
даёт кашу. Здесь блоки ставятся по координатам, которые считает скрипт (обычно сеткой:
колонки — этапы потока, строки — уровни), высота блока подбирается под текст, а частые
ошибки раскладки ловятся проверкой lint() ещё до рендера.

Как пользоваться: скопировать этот файл рядом со своим скриптом-генератором и импортировать.

    from drawio_builder import Diagram

    d = Diagram("Схема")
    api = d.box("API", ["принимает заявки"], x=40, y=80, width=220, kind="green")
    db = d.box("База", ["хранит заявки"], x=340, y=80, width=220)
    d.arrow(api, db, "SQL")
    for warning in d.lint():
        print("ПРОВЕРКА:", warning)
    d.save("scheme.drawio")

Методы возвращают объект Cell. Его x, y, width, height можно менять до save(): файл пишется
по состоянию на момент записи. Источником и целью стрелки может быть любая ячейка, в том
числе рамка.

Побочных эффектов нет, кроме записи файла в save(). Картинку из файла делает render_drawio.py.
Подробности раскладки — references/layout.md, все методы — references/api.md.
"""

import html
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# ---------- палитра ----------
INK = "#1F2328"           # основной текст и обводка кружков
LINE = "#57606A"          # линии и обводка обычных блоков
FRAME_LINE = "#8C959F"
WHITE = "#FFFFFF"

# Виды блоков: заливка и обводка. Цвет несёт смысл, а не украшает:
# один вид — одна роль на всей схеме, роль объясняется в легенде.
KINDS = {
    "plain": (WHITE, LINE),               # обычный блок
    "muted": ("#F6F8FA", LINE),           # второстепенное, справочное, отложенное
    "green": ("#DAFBE1", "#1A7F37"),
    "blue": ("#DDF4FF", "#0969DA"),
    "purple": ("#FBEFFF", "#8250DF"),
    "red": ("#FFEBE9", "#CF222E"),
    "highlight": ("#FFF1D6", "#BC4C00"),  # то, на что надо обратить внимание: развилка, изменение
}
NOTE_FILL, NOTE_LINE = "#FFF8C5", "#BF8700"
BADGE_FILLS = {"open": "#F59E0B", "deferred": "#D0D7DE", "done": "#4AC26B"}

FONT = "fontFamily=Helvetica;"
BADGE_SIZE = 28

# Оценка размеров текста. Точных метрик шрифта здесь нет, поэтому коэффициенты взяты
# с запасом по рендерам draw.io (Helvetica): лучше блок чуть выше, чем обрезанная строка.
CHAR_WIDTH_REGULAR = 0.53   # средняя ширина символа в долях кегля
CHAR_WIDTH_BOLD = 0.60
LINE_HEIGHT = 1.34          # высота строки в долях кегля
TEXT_PAD_X = 16             # отступы текста внутри блока: слева и справа в сумме
TEXT_PAD_Y = 16             # сверху и снизу в сумме
CARD_TITLE_SIZE, CARD_LINE_SIZE = 13, 12   # кегли карточек развилок: card() и text_height() для них
FRAME_TITLE_SIZE = 13


@dataclass
class Cell:
    """Геометрия и текст ячейки — нужны для привязки стрелок и для проверок."""
    id: str
    role: str                      # box, frame, note, badge, text
    x: float
    y: float
    width: float
    height: float
    name: str = ""                 # короткое имя для сообщений проверки
    title: str = ""
    lines: tuple = ()
    title_size: int = 12
    line_size: int = 11
    auto_height: bool = False

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def center(self):
        return (self.x + self.width / 2, self.y + self.height / 2)


@dataclass
class Arrow:
    source: Cell
    target: Cell
    label: str
    exit: tuple
    entry: tuple
    font_size: int = 10


# ---------- оценка текста ----------

def wrapped_line_count(text, inner_width, font_size, bold=False):
    """Сколько строк займёт текст при переносе по словам в блоке шириной inner_width."""
    char_width = font_size * (CHAR_WIDTH_BOLD if bold else CHAR_WIDTH_REGULAR)
    chars_per_line = max(1, int(inner_width / char_width))
    count, current = 1, 0
    for word in text.split():
        length = len(word)
        if current == 0:
            current = length
        elif current + 1 + length <= chars_per_line:
            current += 1 + length
        else:
            count += 1
            current = length
        # слово длиннее строки draw.io не переносит, оно просто вылезет — считаем как одну строку
    return count


def text_height(title, lines, width, title_size=12, line_size=11):
    """Оценка высоты блока под заголовок и строки при заданной ширине."""
    inner_width = width - TEXT_PAD_X
    height = TEXT_PAD_Y
    if title:
        height += wrapped_line_count(title, inner_width, title_size, bold=True) * title_size * LINE_HEIGHT
    for line in lines:
        height += wrapped_line_count(line, inner_width, line_size) * line_size * LINE_HEIGHT
    return int(math.ceil(height / 2.0) * 2)


def label_html(title, lines=(), title_size=12, line_size=11):
    """HTML-подпись ячейки: жирный заголовок и строки под ним.

    Весь текст экранируется: литералы вроде <имя> иначе превратятся в теги и пропадут.
    """
    parts = []
    if title:
        parts.append(f'<b style="font-size:{title_size}px">{html.escape(title)}</b>')
    for line in lines:
        parts.append(f'<span style="font-size:{line_size}px">{html.escape(line)}</span>')
    return "<br>".join(parts)


class Diagram:
    """Схема draw.io: накапливает ячейки и стрелки, проверяет раскладку, пишет файл."""

    def __init__(self, name="Схема"):
        self.name = name
        self.cells = []
        self.arrows = []
        self._xml_cells = []     # (тег, атрибуты, геометрия) в порядке отрисовки
        self._counter = 0

    # ---------- внутреннее ----------

    def _next_id(self, prefix):
        self._counter += 1
        return f"{prefix}{self._counter}"

    def _add_vertex(self, role, label, x, y, width, height, style, name="", title="", lines=(),
                    title_size=12, line_size=11, auto_height=False):
        cell = Cell(self._next_id("n"), role, x, y, width, height, name or title or label,
                    title, tuple(lines), title_size, line_size, auto_height)
        self.cells.append(cell)
        self._xml_cells.append(("vertex", {"id": cell.id, "value": label, "style": style}, cell))
        return cell

    @staticmethod
    def _box_style(fill, line, dashed=False, stroke_width=1, rounded=True):
        dash = "dashed=1;dashPattern=6 4;" if dashed else ""
        corners = "rounded=1;arcSize=6;" if rounded else "rounded=0;"
        return (f"{corners}whiteSpace=wrap;html=1;{FONT}fillColor={fill};strokeColor={line};"
                f"strokeWidth={stroke_width};fontColor={INK};align=left;verticalAlign=top;"
                f"spacingLeft=8;spacingRight=6;spacingTop=5;{dash}")

    # ---------- блоки ----------

    def box(self, title, lines=(), *, x, y, width, height=None, kind="plain", dashed=False,
            title_size=12, line_size=11):
        """Блок с жирным заголовком и строками. Без height высота подбирается под текст."""
        fill, line = KINDS[kind]
        auto = height is None
        if auto:
            height = text_height(title, lines, width, title_size, line_size)
        return self._add_vertex("box", label_html(title, lines, title_size, line_size), x, y, width, height,
                                self._box_style(fill, line, dashed), title=title, lines=lines,
                                title_size=title_size, line_size=line_size, auto_height=auto)

    @staticmethod
    def _frame_style(kind, dashed, stroke_width, filled):
        fill, line = KINDS[kind]
        if kind == "muted":
            line = FRAME_LINE
        if not filled:
            fill = "none"
        dash = "dashed=1;dashPattern=8 4;" if dashed else ""
        return (f"rounded=0;whiteSpace=wrap;html=1;{FONT}fillColor={fill};strokeColor={line};"
                f"strokeWidth={stroke_width};fontColor={INK};fontStyle=1;fontSize={FRAME_TITLE_SIZE};align=left;"
                f"verticalAlign=top;spacingLeft=10;spacingTop=4;{dash}")

    def frame(self, title, *, x, y, width, height, kind="muted", dashed=False, stroke_width=1, filled=True):
        """Рамка-контейнер с подписью в левом верхнем углу. Рисуй рамки раньше блоков внутри них:
        порядок вызовов — это порядок слоёв. filled=False — только цветная обводка, без заливки:
        так внутренняя рамка отличается от внешней цветом, а не пунктиром."""
        return self._add_vertex("frame", html.escape(title), x, y, width, height,
                                self._frame_style(kind, dashed, stroke_width, filled), name=title or "рамка")

    def frame_around(self, title, cells, *, pad=18, top_pad=40, kind="muted", dashed=False, stroke_width=1,
                     filled=True):
        """Рамка вокруг уже созданных ячеек: размер считается по ним, слой — под ними.

        Удобнее frame(), когда блоки с автовысотой: не надо заранее считать высоту рамки.
        top_pad — место под подпись рамки. Вызывай после equal_heights(), иначе рамка
        посчитается по старым размерам.
        """
        left = min(cell.x for cell in cells) - pad
        top = min(cell.y for cell in cells) - top_pad
        right = max(cell.right for cell in cells) + pad
        bottom = max(cell.bottom for cell in cells) + pad
        frame = self._add_vertex("frame", html.escape(title), left, top, right - left, bottom - top,
                                 self._frame_style(kind, dashed, stroke_width, filled), name=title or "рамка")
        # Рамка создана последней, а лежать должна под своими ячейками: переносим её в списке
        # отрисовки перед самой нижней из них.
        entry = self._xml_cells.pop()
        inner_ids = {cell.id for cell in cells}
        position = min(index for index, (_, attributes, _) in enumerate(self._xml_cells)
                       if attributes["id"] in inner_ids)
        self._xml_cells.insert(position, entry)
        return frame

    def note(self, title, lines=(), *, x, y, width, height=None, title_size=12, line_size=11):
        """Жёлтый стикер: пояснение, легенда, вывод. Не часть потока."""
        auto = height is None
        if auto:
            height = text_height(title, lines, width + 4, title_size, line_size) + 4
        style = (f"shape=note;size=14;whiteSpace=wrap;html=1;{FONT}fillColor={NOTE_FILL};strokeColor={NOTE_LINE};"
                 f"fontColor={INK};align=left;verticalAlign=top;spacingLeft=10;spacingRight=8;spacingTop=6;")
        return self._add_vertex("note", label_html(title, lines, title_size, line_size), x, y, width, height,
                                style, title=title, lines=lines, title_size=title_size, line_size=line_size,
                                auto_height=auto)

    def text(self, title, lines=(), *, x, y, width, height=None, title_size=16, line_size=12):
        """Текст без рамки: заголовок схемы, подпись области."""
        if height is None:
            height = text_height(title, lines, width, title_size, line_size)
        style = (f"text;whiteSpace=wrap;html=1;{FONT}strokeColor=none;fillColor=none;fontColor={INK};"
                 f"align=left;verticalAlign=top;")
        return self._add_vertex("text", label_html(title, lines, title_size, line_size), x, y, width, height,
                                style, title=title, lines=lines, title_size=title_size, line_size=line_size)

    def equal_heights(self, *cells):
        """Делает блоки одной высоты — по самому высокому. Для ряда блоков с автовысотой:
        ровный ряд читается как один уровень.

        Вызывай до того, как ставить что-то ниже этого ряда и до frame_around(): блоки
        могут вырасти, а то, что уже посчитано от их старой высоты, не подвинется.
        """
        tallest = max(cell.height for cell in cells)
        for cell in cells:
            cell.height = tallest
        return tallest

    def align_middle(self, reference, *cells):
        """Ставит блоки по вертикали на ось reference (центр к центру). Для цепочки блоков,
        которая должна прийти в середину высокого блока или рамки."""
        middle = reference.y + reference.height / 2
        for cell in cells:
            cell.y = middle - cell.height / 2

    # ---------- кружки и карточки развилок ----------

    def badge(self, label, *, x, y, kind="open"):
        """Кружок с номером. open — надо выбрать, deferred — отложено, done — решено."""
        style = (f"ellipse;whiteSpace=wrap;html=1;aspect=fixed;{FONT}fillColor={BADGE_FILLS[kind]};"
                 f"strokeColor={INK};fontColor={INK};fontStyle=1;fontSize=13;")
        return self._add_vertex("badge", html.escape(str(label)), x, y, BADGE_SIZE, BADGE_SIZE, style,
                                name=f"кружок {label}")

    def badge_on(self, cell, label, *, kind="open", corner="top-right", index=0):
        """Кружок на углу блока. index сдвигает второй и следующие кружки вдоль верхней стороны."""
        half = BADGE_SIZE / 2
        step = BADGE_SIZE + 4
        if corner == "top-right":
            x, y = cell.right - half - index * step, cell.y - half
        elif corner == "top-left":
            x, y = cell.x - half + index * step, cell.y - half
        elif corner == "bottom-right":
            x, y = cell.right - half - index * step, cell.bottom - half
        elif corner == "bottom-left":
            x, y = cell.x - half + index * step, cell.bottom - half
        else:
            raise ValueError(f"corner: ожидается top-right, top-left, bottom-right или bottom-left, получено {corner}")
        return self.badge(label, x=x, y=y, kind=kind)

    def badge_between(self, source, target, label, *, kind="open", offset=(0, -20)):
        """Кружок у стрелки между двумя ячейками: когда развилка про связь («кто создаёт»,
        «каким путём»), а не про блок. Ставится посередине промежутка, offset сдвигает его
        с линии, чтобы не закрыть подпись стрелки."""
        middle_x = (min(source.right, target.right) + max(source.x, target.x)) / 2
        middle_y = (min(source.bottom, target.bottom) + max(source.y, target.y)) / 2
        return self.badge(label, x=middle_x - BADGE_SIZE / 2 + offset[0], y=middle_y - BADGE_SIZE / 2 + offset[1],
                          kind=kind)

    def card(self, number, title, lines=(), *, x, y, width, height=None, kind="highlight", badge_kind="open",
             title_size=CARD_TITLE_SIZE, line_size=CARD_LINE_SIZE):
        """Карточка развилки для панели расшифровки: блок с вариантами и кружок с тем же номером,
        что стоит на схеме."""
        cell = self.box(title, lines, x=x, y=y, width=width, height=height, kind=kind,
                        title_size=title_size, line_size=line_size)
        self.badge_on(cell, number, kind=badge_kind, corner="top-left")
        return cell

    # ---------- стрелки ----------

    @staticmethod
    def _default_sides(source, target):
        """Стороны выхода и входа по взаимному положению блоков.

        Если блоки стоят в ряд или в колонку, точки выбираются на общей части их сторон:
        линия выходит прямой, даже когда блоки разной высоты или ширины. Иначе draw.io
        соединит середины сторон и нарисует излом.
        """
        overlap_top, overlap_bottom = max(source.y, target.y), min(source.bottom, target.bottom)
        overlap_left, overlap_right = max(source.x, target.x), min(source.right, target.right)

        if target.x >= source.right or target.right <= source.x:
            if overlap_bottom > overlap_top:
                line_y = (overlap_top + overlap_bottom) / 2
                exit_y = (line_y - source.y) / source.height
                entry_y = (line_y - target.y) / target.height
            else:
                exit_y = entry_y = 0.5
            if target.x >= source.right:
                return (1, exit_y), (0, entry_y)
            return (0, exit_y), (1, entry_y)

        if overlap_right > overlap_left:
            line_x = (overlap_left + overlap_right) / 2
            exit_x = (line_x - source.x) / source.width
            entry_x = (line_x - target.x) / target.width
        else:
            exit_x = entry_x = 0.5
        if target.y >= source.bottom:
            return (exit_x, 1), (entry_x, 0)
        return (exit_x, 0), (entry_x, 1)

    def arrow(self, source, target, label="", *, dashed=False, exit=None, entry=None, color=None, font_size=10):
        """Стрелка между ячейками. exit и entry — точки на сторонах в долях (x, y): (1, 0.5) — середина
        правой стороны. Без них стороны выбираются по взаимному положению блоков."""
        default_exit, default_entry = self._default_sides(source, target)
        exit = exit or default_exit
        entry = entry or default_entry
        stroke = color or LINE
        style = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;{FONT}endArrow=block;endFill=1;endSize=7;"
                 f"strokeColor={stroke};fontColor={color or INK};fontSize={font_size};labelBackgroundColor={WHITE};"
                 f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
                 f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;")
        if dashed:
            style += "dashed=1;dashPattern=6 4;endArrow=open;endFill=0;"
        self.arrows.append(Arrow(source, target, label, exit, entry, font_size))
        self._xml_cells.append(("edge", {"id": self._next_id("e"), "value": html.escape(label), "style": style,
                                         "source": source.id, "target": target.id}, None))

    def arrow_from_point(self, point, target, label="", *, dashed=True, entry=(0.5, 1), color=None, font_size=10):
        """Стрелка из свободной точки в ячейку: для связей, у которых нет блока-источника на схеме."""
        stroke = color or LINE
        style = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;{FONT}endArrow=open;endFill=0;endSize=7;"
                 f"strokeColor={stroke};fontColor={color or INK};fontSize={font_size};labelBackgroundColor={WHITE};"
                 f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;")
        if dashed:
            style += "dashed=1;dashPattern=6 4;"
        self._xml_cells.append(("edge", {"id": self._next_id("e"), "value": html.escape(label), "style": style,
                                         "target": target.id}, point))

    # ---------- проверки ----------

    def lint(self):
        """Ищет ошибки раскладки, которые видно по геометрии, не дожидаясь рендера.

        Проверки приблизительные (ширина текста оценивается): предупреждение — повод посмотреть
        это место на рендере, отсутствие предупреждений рендер не заменяет.
        """
        warnings = []
        boxes = [c for c in self.cells if c.role in ("box", "note")]
        frames = [c for c in self.cells if c.role == "frame"]

        # 1. Текст не помещается в блок с заданной вручную высотой
        for cell in boxes:
            if cell.auto_height:
                continue
            needed = text_height(cell.title, cell.lines, cell.width, cell.title_size, cell.line_size)
            if needed > cell.height + 2:
                warnings.append(f"текст не помещается: «{cell.name}» — высота {int(cell.height)}, нужно около {needed}")

        # 2. Блоки наезжают друг на друга
        for i, first in enumerate(boxes):
            for second in boxes[i + 1:]:
                if _intersects(first, second) and not _contains(first, second) and not _contains(second, first):
                    warnings.append(f"блоки пересекаются: «{first.name}» и «{second.name}»")

        # 3. Блок пересекает границу рамки: обычно это блок, который не поместился в свою рамку
        for cell in boxes:
            for frame in frames:
                if _intersects(cell, frame) and not _contains(frame, cell) and not _contains(cell, frame):
                    warnings.append(f"блок вылезает за рамку: «{cell.name}» и рамка «{frame.name}»")

        # 3а. Подпись рамки шире рамки: перенесётся на вторую строку и ляжет на блоки внутри
        for frame in frames:
            title_width = len(frame.name) * FRAME_TITLE_SIZE * CHAR_WIDTH_BOLD + 20
            if frame.name != "рамка" and title_width > frame.width:
                warnings.append(f"подпись рамки «{frame.name}» шире рамки ({int(title_width)} > {int(frame.width)}): "
                                f"сократи подпись или расширь рамку")

        # 4. Подпись стрелки шире промежутка между блоками — ляжет поверх блоков
        for arrow in self.arrows:
            if not arrow.label:
                continue
            gap = _gap_along_arrow(arrow)
            label_width = len(arrow.label) * arrow.font_size * CHAR_WIDTH_REGULAR + 6
            if gap is not None and label_width > gap:
                warnings.append(f"подпись «{arrow.label}» шире промежутка ({int(label_width)} > {int(gap)}): "
                                f"стрелка «{arrow.source.name}» → «{arrow.target.name}»; "
                                f"раздвинь блоки или перенеси текст в блок")

        # 5. Прямая стрелка проходит сквозь посторонний блок
        for arrow in self.arrows:
            segment = _straight_segment(arrow)
            if segment is None:
                continue
            for cell in boxes:
                if cell in (arrow.source, arrow.target):
                    continue
                if _segment_crosses(segment, cell):
                    warnings.append(f"стрелка «{arrow.source.name}» → «{arrow.target.name}» проходит сквозь «{cell.name}»")
        return warnings

    # ---------- запись ----------

    def size(self):
        """Размер холста по крайним ячейкам."""
        width = max((c.right for c in self.cells), default=800) + 30
        height = max((c.bottom for c in self.cells), default=600) + 30
        return int(width), int(height)

    def save(self, path):
        """Пишет файл .drawio. Существующий файл перезаписывается целиком."""
        width, height = self.size()
        mxfile = ET.Element("mxfile", host="app.diagrams.net")
        diagram = ET.SubElement(mxfile, "diagram", name=self.name, id="diagram-1")
        model = ET.SubElement(
            diagram, "mxGraphModel", dx="1400", dy="900", grid="1", gridSize="10", guides="1", tooltips="1",
            connect="1", arrows="1", fold="1", page="0", pageScale="1", pageWidth=str(width),
            pageHeight=str(height), math="0", shadow="0")
        root = ET.SubElement(model, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")
        for tag, attributes, extra in self._xml_cells:
            if tag == "vertex":
                cell = ET.SubElement(root, "mxCell", vertex="1", parent="1", **attributes)
                ET.SubElement(cell, "mxGeometry", x=str(extra.x), y=str(extra.y), width=str(extra.width),
                              height=str(extra.height), **{"as": "geometry"})
            else:
                cell = ET.SubElement(root, "mxCell", edge="1", parent="1", **attributes)
                geometry = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
                if extra is not None:  # стрелка из свободной точки
                    ET.SubElement(geometry, "mxPoint", x=str(extra[0]), y=str(extra[1]), **{"as": "sourcePoint"})
        ET.indent(mxfile, space="  ")
        ET.ElementTree(mxfile).write(path, encoding="utf-8", xml_declaration=False)
        return path


# ---------- геометрия для проверок ----------

def _intersects(first, second):
    return (first.x < second.right and second.x < first.right and
            first.y < second.bottom and second.y < first.bottom)


def _contains(outer, inner):
    return (outer.x <= inner.x and outer.y <= inner.y and
            outer.right >= inner.right and outer.bottom >= inner.bottom)


def _gap_along_arrow(arrow):
    """Свободный промежуток между блоками вдоль стрелки. None, если блоки не стоят в ряд или колонку:
    тогда стрелка идёт с изгибом и подписи обычно есть где лечь."""
    source, target = arrow.source, arrow.target
    overlap_y = min(source.bottom, target.bottom) - max(source.y, target.y)
    if overlap_y > 0:
        return max(target.x - source.right, source.x - target.right)
    # Вертикальная стрелка или стрелка с изгибом: подпись ложится сбоку от линии,
    # ширина промежутка ей не мешает
    return None


def _straight_segment(arrow):
    """Отрезок прямой стрелки (точки выхода и входа на одной горизонтали или вертикали), иначе None."""
    source, target = arrow.source, arrow.target
    start = (source.x + source.width * arrow.exit[0], source.y + source.height * arrow.exit[1])
    end = (target.x + target.width * arrow.entry[0], target.y + target.height * arrow.entry[1])
    if abs(start[1] - end[1]) <= 2 or abs(start[0] - end[0]) <= 2:
        return start, end
    return None


def _segment_crosses(segment, cell):
    (x1, y1), (x2, y2) = segment
    left, right = min(x1, x2), max(x1, x2)
    top, bottom = min(y1, y2), max(y1, y2)
    if abs(y1 - y2) <= 2:   # горизонтальный отрезок
        return cell.y < y1 < cell.bottom and left < cell.right and cell.x < right
    return cell.x < x1 < cell.right and top < cell.bottom and cell.y < bottom
