import pathlib
from setuptools import setup, find_packages

setup(
    name="prisl-code",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[],
    entry_points={
        "console_scripts": [
            "prisl-code=prisl_code.prislcode:main",
        ],
    },
    author="rx76d",
    description="Autonomous CLI powered by local LLMs",
    long_description=pathlib.Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    url="https://github.com/rx76d/prisl-code",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)