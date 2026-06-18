PYTHON ?= $(shell [ -f .venv/bin/python ] && echo .venv/bin/python || command -v python3 2>/dev/null || echo python)

.PHONY: setup syntax run

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

syntax:
	$(PYTHON) -B -c 'source = open("app.py").read(); compile(source, "app.py", "exec")'

run:
	$(PYTHON) -m streamlit run app.py


