PYTHON ?= python

.PHONY: setup syntax test database process

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

syntax:
	$(PYTHON) -B -c 'source = open("vision_test.py").read(); compile(source, "vision_test.py", "exec")'
	$(PYTHON) -B -c 'source = open("makeDatabase.py").read(); compile(source, "makeDatabase.py", "exec")'

test:
	$(PYTHON) -m unittest discover -s tests

database:
	$(PYTHON) makeDatabase.py

process:
	$(PYTHON) vision_test.py
