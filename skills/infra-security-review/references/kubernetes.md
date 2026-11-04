# Kubernetes

## RBAC

- `ClusterRoleBinding` на группы `system:serviceaccounts`, `system:authenticated`, `system:unauthenticated` — права у всех.
- `cluster-admin` или `*` в `verbs`/`resources`/`apiGroups` для SA приложения или оператора, которому это не нужно.
- Опасные глаголы и ресурсы, дающие эскалацию:
  - `bind`, `escalate` на роли; `impersonate`;
  - `create` на `pods` (и контроллеры: deployments, jobs, cronjobs) в namespace с привилегированными SA — можно запустить под с чужим SA;
  - `pods/exec`, `pods/attach`, `nodes/proxy`;
  - `get`/`list`/`watch` на `secrets` кластерно — это чтение всех токенов SA;
  - `create` на `serviceaccounts/token`;
  - `update`/`patch` на `validatingwebhookconfigurations`, `mutatingwebhookconfigurations`;
  - `create` на `tokenreviews`/`subjectaccessreviews` (`system:auth-delegator`) для широких групп.
- `automountServiceAccountToken` не отключён у подов, которым API не нужен.

## Поды и рабочие нагрузки

- `privileged: true`, `hostPID`, `hostIPC`, `hostNetwork`, `hostPath` (особенно `/`, `/var/run`, `/etc`, сокеты рантайма), `capabilities.add` (`SYS_ADMIN`, `NET_ADMIN`, `ALL`).
- `runAsUser: 0`, нет `runAsNonRoot`, `allowPrivilegeEscalation` не `false`, `readOnlyRootFilesystem` не задан — в компонентах, которым это не нужно.
- Pod Security Admission: namespace без меток `pod-security.kubernetes.io/enforce` или с `privileged` без причины.
- Job'ы и CronJob'ы с секретами: что они печатают в лог; `backoffLimit` и повторы множат утечки; Job, обречённый падать, долбит внешние системы.

## Образы и поставка

- Плавающие теги: `:latest`, `:v1`, `:main`, ветки. Для провайдеров и операторов, у которых широкие права, — особенно. Закреплять версию или digest.
- Реестры вне доверенного списка; `REGISTRY_SKIP_VERIFY`, `insecureSkipTLSVerify`.
- `kubectl apply -f https://raw.githubusercontent.com/.../main/...` — незакреплённый чужой манифест прямо в кластер.
- Пакеты Crossplane, чарты, CRD из сторонних источников без закреплённой версии.

## Вебхуки и admission

- `failurePolicy: Ignore` у политик безопасности — при падении вебхука защита молча выключается.
- `namespaceSelector`/`objectSelector` с исключениями, через которые можно обойти политику (исключение по метке, которую может поставить владелец namespace).
- Вебхуки с `sideEffects` и широкими правами, вебхук, который может менять поды во всех namespace.

## Сеть

- Нет NetworkPolicy там, где задумана изоляция; `allow all` политики.
- Сервисы `LoadBalancer`/`NodePort` для внутренних компонентов (Vault, ArgoCD, БД, метрики с секретами).
- Метрики и debug-эндпоинты без аутентификации (`unauthenticated_metrics_access`, pprof) — что они раскрывают.

## TLS и проверки

- `VAULT_SKIP_VERIFY: true`, `insecure: true`, `--insecure-skip-tls-verify`, `curl -k`, `verify: false` — в конфигурации, которая едет в кластер.
- Самоподписанные CA, которые доверяются глобально.
