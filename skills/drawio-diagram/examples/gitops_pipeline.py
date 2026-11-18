#!/usr/bin/env python3
"""
Пример генератора схемы: доставка сервиса через GitOps с одной развилкой на выбор.

Показывает приёмы скилла: сетка из колонок и строк, блоки с автовысотой, рамки вокруг
готовых блоков, стрелки в ряд и с изгибом, кружок развилки на схеме и карточка с вариантами
в нижней панели, легенда, проверка lint() перед записью.

Запуск:
    python3 gitops_pipeline.py                 # пишет gitops_pipeline.drawio рядом со скриптом
    python3 gitops_pipeline.py other.drawio    # или в указанный файл
    python3 ../scripts/render_drawio.py gitops_pipeline.drawio

Побочные эффекты: перезаписывает выходной файл .drawio целиком.
"""

import sys
from pathlib import Path

# В примере библиотека берётся из каталога скилла. В своём генераторе скопируй
# drawio_builder.py рядом со скриптом: тогда схему пересоберёт кто угодно без скилла.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from drawio_builder import Diagram  # noqa: E402


def build():
    d = Diagram("Доставка через GitOps")

    # Сетка: колонки — этапы доставки слева направо, строки — сборка и развёртывание.
    # Промежуток 110: в него целиком ложатся короткие подписи стрелок.
    column_width, column_gap = 230, 110
    columns = [40 + index * (column_width + column_gap) for index in range(5)]
    row_build, row_deploy = 130, 320

    d.text("Доставка сервиса через GitOps",
           ["Стрелка идёт от того, кто действует, к тому, с кем он действует. Оранжевый кружок — развилка, варианты внизу."],
           x=40, y=10, width=1500)

    developer = d.box("Разработчик", ["пуш в ветку сервиса"], x=columns[0], y=row_build, width=column_width)
    ci = d.box("CI", ["тесты, сборка образа", "тег образа — короткий хеш коммита"],
               x=columns[1], y=row_build, width=column_width, kind="blue")
    registry = d.box("Реестр образов", ["хранит образ с тегом"], x=columns[2], y=row_build, width=column_width)

    gitops_repo = d.box("GitOps-репозиторий", ["чарт и значения окружения", "тег образа в values"],
                        x=columns[2], y=row_deploy, width=column_width, kind="highlight")
    argocd = d.box("Argo CD", ["сравнивает репозиторий с кластером", "синхронизирует изменения"],
                   x=columns[3], y=row_deploy, width=column_width, kind="green")
    workload = d.box("Нагрузка", ["Deployment с новым образом"], x=columns[4], y=row_deploy, width=column_width)

    # Блоки с автовысотой получаются разной высоты; ряд выравнивается по самому высокому.
    # Делается до рамок: frame_around() считает размер по текущей высоте блоков.
    d.equal_heights(developer, ci, registry)
    d.equal_heights(gitops_repo, argocd, workload)

    d.frame_around("Сборка", [ci, registry])
    d.frame_around("Кластер", [argocd, workload])

    d.arrow(developer, ci, "пуш")
    d.arrow(ci, registry, "образ")
    # Стрелка с изгибом: стороны выхода и входа заданы явно, чтобы линия не шла сквозь блоки.
    d.arrow(ci, gitops_repo, "новый тег", exit=(0.5, 1), entry=(0, 0.5))
    d.arrow(gitops_repo, argocd, "читает", dashed=True)
    d.arrow(argocd, workload, "применяет")
    d.arrow(workload, registry, "pull образа", dashed=True, exit=(0.5, 0), entry=(1, 0.5))

    d.badge_on(gitops_repo, 1)

    d.note("Обозначения", [
        "• сплошная стрелка — запись или изменение",
        "• пунктир — чтение",
        "• оранжевая заливка — зависит от развилки",
    ], x=columns[0], y=row_deploy - 10, width=column_width + 40)

    # Панель развилок под схемой. Высота рамки считается по карточке, а не подбирается на глаз.
    panel_width = columns[4] + column_width - 40
    panel_top = workload.bottom + 70
    card = d.card(1, "Кто обновляет тег образа в GitOps-репозитории", [
        "★ А. CI коммитит новый тег после сборки. Просто и видно в истории; CI нужен доступ на запись.",
        "Б. Argo CD Image Updater следит за реестром. CI без доступа к репозиторию; ещё один компонент.",
    ], x=60, y=panel_top + 44, width=700)
    panel = d.frame_around("Развилки — ответ в виде «1 — А»", [card], pad=20, top_pad=44, kind="plain")
    # Рамку панели растягиваем на ширину схемы: геометрию ячейки можно менять до save().
    panel.width = panel_width

    return d


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).with_suffix(".drawio"))
    diagram = build()
    for warning in diagram.lint():
        print("ПРОВЕРКА:", warning)
    print("Схема записана:", diagram.save(output))
