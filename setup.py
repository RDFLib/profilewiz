from setuptools import setup, find_packages

setup(
    name="profilewiz",
    version="0.4",
    #packages=["profilewiz"],
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'profilewiz = profilewiz.profilewiz:main'
        ]
    },
    url="https://github.com/RDFLib/profilewiz",
    license="CCby",
    install_requires=["mimeparse", "rdflib>=5.0.0", "rdflib-jsonld", "requests", "prompt_toolkit"],
    author="Rob Atkinson",
    author_email="",
    description="A tool for analysing, extracting and converting profiles of data models for Linked Data",
)
