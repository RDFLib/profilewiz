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


