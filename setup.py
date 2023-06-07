import os.path

from setuptools import setup
from setuptools.command.build_py import build_py


class build_with_pylib_hooks(build_py):
    def run(self):
        super().run()

        for file_to_copy in ["py.pyi", "pytest_py.pth"]:
            src = os.path.join("src", file_to_copy)
            dst = os.path.join(self.build_lib, file_to_copy)
            self.copy_file(src, dst)


if __name__ == "__main__":
    setup(cmdclass={"build_py": build_with_pylib_hooks})
