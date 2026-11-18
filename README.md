# claude-skills

Скиллы для [Claude Code](https://docs.anthropic.com/en/docs/claude-code) для эксплуатации платформ на Kubernetes: GitOps, Helm, ArgoCD, Crossplane, HashiCorp Vault — и для схем, которыми эту работу объясняют.

## Скиллы

| Скилл | Что делает |
| --- | --- |
| [infra-security-review](skills/infra-security-review/SKILL.md) | Ревью безопасности инфраструктурной работы — своей и чужой: MR и диффы, Helm и values, манифесты Kubernetes и RBAC, ArgoCD, Crossplane, роли и политики Vault, shell-скрипты эксплуатации, живое состояние в режиме только чтения |
| [drawio-diagram](skills/drawio-diagram/SKILL.md) | Схемы в формате draw.io: архитектура, потоки, раскладка по уровням, схема с развилками на выбор. Собирает скриптом по сетке, проверяет наезды, рендерит и смотрит результат до сдачи |

## infra-security-review

Ищет то, из-за чего инфраструктура становится доступна шире, чем задумано:
- секреты в git, логах Job'ов, аргументах процессов, статусах CR;
- роли Vault, привязанные к любым ServiceAccount с доступом ко всему KV;
- политики, равные root (право переписать свою политику);
- mount'ы auth одного контура в Vault другого;
- RBAC с эскалацией;
- плавающие теги образов и провайдеров;
- разрушительные `syncOptions` и `deletionPolicy`;
- скрипты, печатающие токены.

Принципы:
- **только чтение** — ревью ничего не меняет, исправления идут предложением;
- **правила окружений проекта выше скилла** — если в `CLAUDE.md` сказано, что prod только с разрешения, скилл туда не ходит;
- **секреты не цитируются** — только тип, место и первые символы, утечка выносится в начало отчёта с рекомендацией ротации;
- **своя работа проверяется так же строго, как чужая.**

Чеклисты разбиты по темам в [`references/`](skills/infra-security-review/references/): secrets, vault, kubernetes, gitops-helm, crossplane, scripts и формат отчёта.

## drawio-diagram

Делает схему, которую человек откроет в [draw.io](https://www.drawio.com/) и будет править и обсуждать:
- схема пишется скриптом-генератором, а не руками в XML: координаты считает код по сетке;
- библиотека подбирает высоту блока под текст и до рендера ловит наезды блоков, подписи шире промежутка, стрелки сквозь блоки;
- схема рендерится в PNG и просматривается по плиткам в натуральную величину — без этого она не считается готовой;
- для схем «что выбрать» — кружки с номерами на спорных местах и панель с вариантами: отвечать можно «3 — Б».

На выходе три файла: `.drawio` для правки, `.png` для просмотра и генератор, которым схему пересоберёт кто угодно.

Нужны Python 3.9+ и [draw.io Desktop](https://github.com/jgraph/drawio-desktop/releases) с командой `drawio`; для плиток — Pillow. Без draw.io файл собирается, но рендер не проверяется, и скилл об этом скажет.

Справочники: [раскладка](skills/drawio-diagram/references/layout.md), [методы библиотеки](skills/drawio-diagram/references/api.md), [пример](skills/drawio-diagram/examples/gitops_pipeline.py).

## Установка

Для текущего пользователя:

```bash
git clone https://github.com/onixsib/claude-skills.git ~/src/claude-skills
ln -s ~/src/claude-skills/skills/infra-security-review ~/.claude/skills/infra-security-review
ln -s ~/src/claude-skills/skills/drawio-diagram ~/.claude/skills/drawio-diagram
```

Для одного проекта — скопировать каталог скилла в `.claude/skills/` репозитория.

Claude Code подхватывает скиллы при старте сессии. Вызов — по имени (`/infra-security-review`, `/drawio-diagram`) или просьбой: «проверь MR на безопасность», «нарисуй схему».

## Лицензия

[MIT](LICENSE)
