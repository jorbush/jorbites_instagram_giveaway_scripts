.PHONY: venv update-deps fmt

venv:
	python -m venv venv

update-deps:
	pip freeze > requirements.txt

fmt:
	autopep8 --recursive --exclude .venv --in-place .
