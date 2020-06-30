# profilewiz
A tool to support round-tripping between modular and flattened versions of profiles of data models expressed using OWL, JSON-Schema, SHACL etc.

## Status
In development, focussed on Use Case 1

## Use Cases
1. Take a data model (such as an OWL ontology) containing copied (and potentially modified) versions of definitons from "standard" models
, intended to document a profile of those external models, and build a better Modular version that contains clear expression of the intended constraints on the original model, and create implementation resources such as JSON-LD contexts with imports of reusable, cachable modules. (Flattened => Modular)
2. (Modular Model => Flattened)  Take a modular profile hierarchy and create "flattened" versions with no requirement for imports
3. Consistency checking of profiles with base specifications.
4. Extracting data models from implementation views - such as JSON-schema and JSON-LD context documents

## Installation
Clone repository.

run python profilewiz --help

## Usage

usage: profilewiz.py [-h] [-o [OUTPUT]] [-q] [-r] [-p P [P ...]] input

Create JSON context, schema and other views of an ontology

positional arguments:
  input                 input file containing ontology in TTL format

optional arguments:
  -h, --help            show this help message and exit
  -o [OUTPUT], --output [OUTPUT]
                        output file
  -q, --qnames_only     use qnames only for JSON elements
  -r, --force_relative  use relative filenames and cached copies for imports
  -p P [P ...], --profiles P [P ...]
                        file name or URL of profiles model with pre-configured
                        resource locations

