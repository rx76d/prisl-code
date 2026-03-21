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
    python_requires=">=3.7",
)