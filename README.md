# Лабораторна робота №4 — PC Components API + React + PostgreSQL + Helm

Навчальна демонстрація всіх трьох частин лабораторної з CI/CD. Продовжує REST API `GET/POST/PUT/DELETE /api/items` з попередньої роботи. **Перед переносом в наявний репозиторій зробіть окрему гілку та збережіть свої попередні файли.** Приклад є завершеним референсним варіантом, а не автоматичним редагуванням вашого GitHub-репозиторію.

## Архітектура

Browser -> React SPA (Nginx) -> `/api/items` -> FastAPI -> SQLAlchemy -> PostgreSQL (StatefulSet, PV, PVC). Окремий міграційний контейнер запускає `alembic upgrade head` як Kubernetes Job; Job створюється Helm `post-install` та `post-upgrade` hooks. Ingress необов'язковий для локального запуску: порт-форвардинг frontend працює через Nginx reverse-proxy до API.

## Вміст

- `app/` — FastAPI і SQLAlchemy Code-First ORM.
- `alembic/` — незалежні, версійовані міграції.
- `tests/` — тести API на ізольованій SQLite БД.
- `frontend/` — React/Vite SPA для CRUD, production Nginx.
- `Dockerfile.api` — образ API.
- `Dockerfile.migration` — окремий консольний образ міграцій.
- `frontend/Dockerfile` — багатостадійна збірка React/Nginx.
- `k8s/pc-components/` — Helm Chart, який встановлює Deployment, StatefulSet, Service, PV, PVC, StorageClass, Secret, Job (hook) та необов'язковий Ingress.
- `.github/workflows/lab4-ci.yml` — тести, frontend build, helm lint/template/package, GitHub artifact, Docker Hub push трьох образів на `main`.

## 0. Передумови на Windows 11

Встановлені Docker Desktop (Linux containers), Git/Git Bash, Python (3.12+), Node.js (22), kubectl, kind (із лабораторної 3). Додатково Helm у **PowerShell**:

```powershell
winget install Helm.Helm
```

Перезапустіть Git Bash і виконайте:

```bash
docker version
kubectl version --client
kind version
helm version
python --version
node --version
npm --version
```

## 1. Локальний backend (Git Bash із кореня проєкту)

```bash
py -3.12 -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Якщо `py -3.12` відсутній, але є Python 3.12+, використайте `python -m venv .venv`. SQLite у `local-dev.db` створюється тільки для локального запуску без PostgreSQL; усередині Kubernetes використовуватиметься PostgreSQL.

Перевірка: http://localhost:8000/docs, http://localhost:8000/api/items. Для зупинки Ctrl+C.

## 2. Локальний frontend (другий Git Bash)

```bash
cd frontend
npm install
npm run build
npm run dev
```

Відкрити http://localhost:5173 . Vite proxy перенаправляє `/api/` у локальний backend на порту 8000 (той має працювати). Перевірте додавання, перегляд, редагування й видалення товару.

## 3. Контейнери й kind (Git Bash у корені проєкту)

Запустіть Docker Desktop, перевірте `kind get clusters`. Приклад використовує ваш попередній kind-кластер `lectures` та його worker `lectures-worker`. Якщо кластер іншого імені, коригуйте `--name`, `kubectl config use-context` і `db.storage.nodeName`.

```bash
kubectl config use-context kind-lectures
kubectl get nodes -o wide
kubectl get storageclass

docker build -t pc-components-api:lab -f Dockerfile.api .
docker build -t pc-components-migrator:lab -f Dockerfile.migration .
docker build -t pc-components-frontend:lab -f frontend/Dockerfile ./frontend

docker images | grep pc-components
kind load docker-image pc-components-api:lab --name lectures
kind load docker-image pc-components-migrator:lab --name lectures
kind load docker-image pc-components-frontend:lab --name lectures
```

Імпорт до kind важливий: образи збираються в Docker Desktop, а Kubernetes запускає контейнери на окремих вузлах kind.

## 4. Створення Helm Chart, перевірка і встановлення

Готовий Helm Chart вже міститься у `k8s/pc-components`. Команда `helm create k8s/pc-components` потрібна **для створення стартового chart з нуля**, тому **не виконуйте її поверх готових шаблонів**. Для демонстрації формату: `helm create k8s/demo-chart` і після огляду видаліть `k8s/demo-chart`.

```bash
helm show chart ./k8s/pc-components
helm lint ./k8s/pc-components -f ./k8s/values.lab.yaml --strict
helm template lab ./k8s/pc-components -n webapp-lab -f ./k8s/values.lab.yaml > rendered.yaml
```

При першому запуску слід мати хоча б один Ready worker node. `values.lab.yaml` вказує `lectures-worker`: перевірте `kubectl get nodes` і замініть цей параметр, якщо назва відрізняється.

Створіть release у namespace (пароль **лише демонстраційний**, не використовуйте для реальних даних):

```bash
helm upgrade --install lab ./k8s/pc-components \
  -n webapp-lab --create-namespace \
  -f ./k8s/values.lab.yaml \
  --set-string db.auth.password=lab-local-12345 \
  --wait --wait-for-jobs --timeout 10m
```

Міграція запускається як Helm hook `post-install`/`post-upgrade` і виконує `alembic upgrade head`. PostgreSQL використовує *статичні* StorageClass/PV/PVC на файловій системі worker вузла kind. Це лабораторний варіант, не production storage. `kind delete cluster` знищує файли на вузлах.

## 5. Перевірка

```bash
helm list -n webapp-lab
helm status lab -n webapp-lab
kubectl get deploy,sts,pods,svc,pv,pvc,jobs -n webapp-lab
kubectl get pv
kubectl logs -n webapp-lab job/lab-migration
kubectl get ingress -n webapp-lab
```

При **успішному** встановленні очікуємо: `lab-postgres-0` Running, API і frontend Ready, `lab-migration` Completed, PVC Bound. `Job` — Helm hook, тому його може не бути в `helm get manifest`, але він відображається в `helm get hooks`.

У новому терміналі:

```bash
kubectl port-forward -n webapp-lab svc/lab-frontend 8080:80
```

Відкрийте http://localhost:8080 , створіть товар, оновіть сторінку, відредагуйте та видаліть його. Потім створіть новий товар, перезапустіть pod backend і переконайтеся, що запис не зник: `kubectl rollout restart deployment/lab-api -n webapp-lab`. Цим перевіряється, що стан зберігається в PostgreSQL, а не в пам'яті API.

## 6. Ingress (додаткова частина відповідно до додатка А)

Chart містить маршрути `/api` → API, `/` → frontend; браузер використовує відносний шлях `/api/items` з того самого origin, тож не потрібно hard-code внутрішню pod-адресу. Ingress-ресурс **не** встановлює Ingress Controller. Замість застарілого community ingress-nginx варто використати підтримуваний Traefik.

Якщо потрібен доступ через Ingress, установіть підтримуваний контролер, наприклад Traefik за [офіційною інструкцією](https://doc.traefik.io/traefik/setup/kubernetes/), переконайтеся, що `kubectl get ingressclass` показує клас `traefik`, а потім:

```bash
helm upgrade --install lab ./k8s/pc-components \
  -n webapp-lab -f ./k8s/values.lab.yaml \
  --set ingress.enabled=true \
  --set ingress.className=traefik \
  --set-string db.auth.password=lab-local-12345 \
  --wait --wait-for-jobs --timeout 10m
kubectl get ingress -n webapp-lab
```

Домен `pc-components.lab.test` потрібно зв'язати з доступним портом/адресою контролера. Для локального демонстраційного port-forward до Traefik можна використовувати `curl -H 'Host: pc-components.lab.test' http://localhost:8081/api/items` після `kubectl port-forward -n traefik svc/traefik 8081:80`. У Windows для відкриття у браузері можна додати `127.0.0.1 pc-components.lab.test` у hosts, тоді відкрити http://pc-components.lab.test:8081 (за умови, що port-forward до Traefik активний).

## 7. Пакування та GitHub Actions

```bash
mkdir -p dist
helm package ./k8s/pc-components --destination dist
helm show chart ./dist/pc-components-0.1.0.tgz
```

У GitHub repository `Settings > Secrets and variables > Actions` додайте два **repository secrets**:

- `DOCKERHUB_USERNAME` — логін Docker Hub.
- `DOCKERHUB_TOKEN` — Docker Hub access token (не пароль акаунта).

Після `git add`, `git commit` і `git push` у гілку `main` GitHub Actions:
1. Тестує backend з SQLite (ізольовані тести).
2. Збирає React.
3. Перевіряє Helm Chart за допомогою lint + template.
4. Створює `pc-components-0.1.0.tgz` та зберігає в артефактах запуску.
5. Збирає та публікує три Docker-образи до Docker Hub із тегами `latest` та SHA коміту.

Workflow для pull request лише тестує та пакує chart, без push образів. Після успішного CI можна перевстановити Kubernetes release з Docker Hub (якщо репозиторії образів публічні або налаштовано imagePullSecrets):

```bash
helm upgrade --install lab ./k8s/pc-components \
  -n webapp-lab -f ./k8s/values.lab.yaml \
  --set api.image.repository=YOUR_DOCKERHUB_USERNAME/pc-components-api \
  --set api.image.tag=latest \
  --set frontend.image.repository=YOUR_DOCKERHUB_USERNAME/pc-components-frontend \
  --set frontend.image.tag=latest \
  --set migration.image.repository=YOUR_DOCKERHUB_USERNAME/pc-components-migrator \
  --set migration.image.tag=latest \
  --set-string db.auth.password=lab-local-12345 \
  --wait --wait-for-jobs --timeout 10m
```

Замініть `YOUR_DOCKERHUB_USERNAME` на ваш Docker Hub username. Використовуйте тег SHA замість latest у відтворюваних розгортаннях.

## Діагностика

```bash
kubectl describe pod POD_NAME -n webapp-lab
kubectl logs -n webapp-lab deployment/lab-api
kubectl logs -n webapp-lab statefulset/lab-postgres
kubectl logs -n webapp-lab job/lab-migration
kubectl describe pvc lab-postgres-data -n webapp-lab
kubectl get events -n webapp-lab --sort-by=.lastTimestamp
helm get values lab -n webapp-lab
helm get hooks lab -n webapp-lab
helm history lab -n webapp-lab
```

- `ImagePullBackOff`: перевірити `kind load docker-image`, `image.repository`, `image.tag`, namespace та стан вузлів.
- `Pending` на PostgreSQL/PVC: перевірити назву worker у `db.storage.nodeName` і стан PV/PVC; `kubectl get nodes`.
- `connection refused`: перевірити, чи працює PostgreSQL, Service і env API.
- `relation "items" does not exist`: перевірити логи Job та `alembic upgrade head`.
- Nginx `502`: API ще не Ready або неправильний `API_UPSTREAM`.
- `helm timeout`: команда не доводить, який компонент винен; дивіться `describe`, `events`, логи.

## Видалення

```bash
helm uninstall lab -n webapp-lab
```

**Увага:** це видаляє об'єкти release, але PV має reclaim policy `Retain`, а локальні файли в worker можуть залишитися. Не видаляйте цілі кластери чи PVC з іншими даними без резервної копії.

## Що продемонструвати на захисті

1. Локальні CRUD-тести, браузер та `/docs` FastAPI.
2. `docker images` — три окремі образи; успішний CI та Docker Hub.
3. `helm lint`, `helm template`, `helm package`.
4. `kubectl get` — API/SPA Deployment, PostgreSQL StatefulSet, PV/PVC/StorageClass, migration Job, Services, Secret (не показуйте пароль).
5. Логи міграції: `Running upgrade -> 001_create_items`.
6. CRUD у браузері після Helm install і збереження товару після перезапуску API.
7. GitHub Actions artifact `pc-components-helm-chart` з файлом `.tgz`.
