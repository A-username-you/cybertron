from setuptools import setup, find_packages
setup(
    name="cybertron",
    version="2.1.0",
    description="Cybertron AI — Security Automation Framework",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "pydantic>=2.0",
        "pydantic-settings>=2.0",
        "structlog>=23.0",
        "tenacity>=8.2",
        "pyyaml>=6.0",
    ],
)
