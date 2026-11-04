# claude-skills

Скиллы для [Claude Code](https://docs.anthropic.com/en/docs/claude-code) для эксплуатации платформ на Kubernetes: GitOps, Helm, ArgoCD, Crossplane, HashiCorp Vault.

## Скиллы

| Скилл | Что делает |
| --- | --- |
| [infra-security-review](skills/infra-security-review/SKILL.md) | Ревью безопасности инфраструктурной работы — своей и чужой: MR и диффы, Helm и values, манифесты Kubernetes и RBAC, ArgoCD, Crossplane, роли и политики Vault, shell-скрипты эксплуатации, живое состояние в режиме только чтения |

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

## Установка

Для текущего пользователя:

```bash
git clone https://github.com/onixsib/claude-skills.git ~/src/claude-skills
ln -s ~/src/claude-skills/skills/infra-security-review ~/.claude/skills/infra-security-review
```

Для одного проекта — скопировать каталог скилла в `.claude/skills/` репозитория.

Claude Code подхватывает скилл при старте сессии. Вызов — `/infra-security-review` или просьбой вида «проверь MR на безопасность».

## Лицензия

[MIT](LICENSE)
