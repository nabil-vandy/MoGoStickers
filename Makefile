PYTHON ?= $(shell [ -f .venv/bin/python ] && echo .venv/bin/python || command -v python3 2>/dev/null || echo python)

.PHONY: setup syntax run

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

syntax:
	$(PYTHON) -m py_compile app.py db.py auth.py gemini.py changelog.py

run:
	$(PYTHON) -m streamlit run app.py


