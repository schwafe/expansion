"""
Put the project root on `sys.path` for the tests in `tests/`.

The modules under test live at the top level, so pytest has to be able to
import them from anywhere. Its default import mode adds the directory of
every conftest.py it loads -- this file exists for that alone, which is why
it is empty otherwise.
"""
