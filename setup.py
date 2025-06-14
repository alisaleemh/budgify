# setup.py
from setuptools import setup, find_packages

setup(
    name="budgify",
    version="0.1.0",
    description="A modular CLI for importing and categorizing bank transactions",
    author="Your Name",
    author_email="you@example.com",
    url="https://github.com/yourusername/budgify",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "click>=7.0",
        "pyyaml>=5.3",
        "pandas>=1.1",
        "openpyxl>=3.0",
        "xlrd>=2.0.1",
    ],
    entry_points={
        "console_scripts": [
            "budgify=transaction_tracker.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)