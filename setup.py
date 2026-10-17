"""Bundle the authored schemas and public language fixtures into installed packages."""
from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildLanguageResources(build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        package = Path(self.build_lib) / "tvl"
        shutil.copytree(root / "spec/grammar", package / "spec/grammar", dirs_exist_ok=True)
        shutil.copytree(
            root / "conformance/cases/runtime", package / "conformance/cases/runtime",
            dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"),
        )


setup(cmdclass={"build_py": BuildLanguageResources})
