from setuptools import setup, find_packages

setup(
    name="cybertron",
    version="3.0.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "cybertron.ui.web_static": ["*", "**/*"],
    },
    entry_points={
        "console_scripts": [
            "cybertron=cybertron.cli:main",
        ],
    },
)
