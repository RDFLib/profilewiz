from setuptools import setup

setup(
    name="profilewiz",
    version="0.1",
    packages=["profilewiz"],
    url="https://github.com/RDFLib/profilewiz",
    license="CCby",
    install_requires=["mimeparse", "rdflib>=5.0.0", "rdflib-jsonld", "requests"],
    author="Rob Atkinson",
    author_email="",
    description="A tool for analysing, extracting and converting profiles of data models for Linked Data",
)
