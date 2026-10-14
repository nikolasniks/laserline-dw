.PHONY: install migrate sync report test lint deploy connector

install:
	pip install -r requirements-dev.txt

migrate:
	./scripts/migrate.sh

sync:          ## extract + transform once, locally
	PYTHONPATH=src python -c "from laserline.handlers import sync_handler as h; print(h({}, None))"

report:
	PYTHONPATH=src python -c "from laserline.handlers import weekly_report_handler as h; print(h({}, None))"

connector:
	PYTHONPATH=src python -m laserline.connector.server

test:
	pytest -q

lint:
	ruff check src tests

deploy:
	sam build -t infra/template.yaml && sam deploy --guided
