from Frame import Frameset
from utils import getdeftoken

JSONTYPES = {'None': "string",
             "http://www.w3.org/2001/XMLSchema#string": "string",
             "http://www.w3.org/2001/XMLSchema#int": "integer",
             "http://www.w3.org/2001/XMLSchema#decimal": "number",
             "http://www.w3.org/2001/XMLSchema#boolean": "boolean",
             }


def to_json_datatype(range):
    """ create a json schema compatible data type description from a property range"""
    try:
        return JSONTYPES[str(range)]
    except:
        return "object"


def make_schema(ontid, g,  frames: Frameset):
    """ make a JSON Schema using a set of frame descriptions for each object"""

    schema = {"$schema": "http://json-schema.org/schema#",
              "$id": str(ontid) + "?_profile=jsonschema",
              "type": "object",
              "properties": {}}

    for classuri, frame in frames.frameset.items():
        class_name = getdeftoken(g,str(classuri))
        class_schema = {"type": "object", "properties": {}, 'required': []}
        for propid,prop in frame.props.items():
            propname = getdeftoken(g,str(propid))
            if 'propRange' not in prop:
                prop['propRange'] = None
            if not 'maxCard' in prop  or prop['maxCard'] > 1:
                propschema = {"type": "array", "items": {"type": to_json_datatype(prop['propRange'])}}
            else:
                propschema = {"type": to_json_datatype(prop['propRange'] ) }
            if 'minCard' in prop and prop['minCard'] > 0:
                class_schema['required'].append(propname)

            class_schema['properties'][propname] = propschema

        schema['properties'].update({class_name: class_schema})
    return schema
