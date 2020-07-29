import re

from rdflib import RDF, RDFS, Graph, URIRef, PROF, Literal, OWL
from rdflib.namespace import split_uri, DCTERMS, SKOS

known = { 'http://www.w3.org/2004/02/skos/core': 'skos',
          'http://purl.org/dc/terms' : 'dcterms'
          }


RDFS_TYPES = (RDFS.Class, RDF.Property)
RDFS_RELS = (RDFS.range, RDFS.subPropertyOf, RDFS.subClassOf)
OWL_TYPES = (OWL.Class,)
OWL_RELS = (OWL.DatatypeProperty,OWL.ObjectProperty)
LABELS = (DCTERMS.title, RDFS.label, SKOS.prefLabel)
DESCS = (DCTERMS.description, SKOS.definition, RDFS.comment )

def get_objs_per_namespace(g, ontid, typesfilter=RDFS_TYPES+OWL_TYPES, relsfilter=RDFS_RELS+OWL_RELS ):
    """ return a dict with a dict of objects and types per namespace in graph
    :param g: Graph
    :return: Dict of { ns , Dict of {object,type} }
    """
    res = {}
    decs = set(())
    try:
        ont_ns, onttoken = split_uri(ontid)
    except:
        ont_ns, onttoken = split_uri(ontid[:-1])
    for dec_type in typesfilter:
        for dec in g.subjects(predicate=RDF.type, object=dec_type):
            decs.add( dec)
    for decrel in relsfilter:
        for dec in g.subjects(predicate=decrel):
            decs.add(dec)

    for s in decs:
        for  p, o in g.predicate_objects(s):
            type = None
            if p == RDF.type:
                type = o

            try:
                (ns, qname) = split_uri(str(s))
            except:
                try:
                    (ns, qname) = split_uri(str(s)[:-1])
                except:
                    continue  # probs a Bnode
            # if is an ontology declaration object restore full URL as namespace
            if ns == ont_ns:
                ns = str(s)
            if ns not in res:
                res[ns] = {}
            if type or str(s) not in res[ns]:
                res[ns][str(s)] = type
    return res

def is_class(objtype):
    """ return true if the type is a Class object"""
    return objtype in ( RDFS.Class, OWL.Class)

def gettype(ontscope, importclosure, prop):
    """get a property type

    looks at the declared range - or walks subProperty hierarchy looking for one
    :param ontscope: Ontology graph to use
    :param importclosure: imported ontologies to search if not found
    :param prop: property to locate
    :return: RDF IRI node with property range"""
    proptype = ontscope.value(prop, RDFS.range)
    return proptype


def getonttoken(url):
    """returns a candidate token from a URL

    for making filenames from the last part of an URI path before file extensions and queries """
    if url in known :
        return known[url]
    return re.sub('^[^\?]*/([a-zA-Z][^/?#]*).*$', r"\1", url)


def get_ont(graph):
    """ return URI of declared ontology in a graph """
    return graph.value(predicate=RDF.type, object=OWL.Ontology)


def extract_objs_in_ns(g, ns, objlist=None):
    """ returns a graph of objects in g in ns, including blank node contents

    if objlist is provided then all objects in list will be used, otherwise all objects will be scanned with get_obj_by_ns()
    :param g: source graph
    :param ns: namespace to extract (string)
    :param objlist: list of objects to extract
    """
    newg = Graph()
    if not objlist:
        objlist = get_objs_per_namespace(g)[ns].keys()
    o: object
    for o in objlist:
        for p, v in g.predicate_objects(URIRef(o)):
            newg.add((URIRef(o), p, v))
    return newg


def get_object_labels(g,id):
    """ get a dict of label predicates and labels """
    return( get_object_preds(g,id,LABELS))


def get_object_descs(g,id):
    """ get a dict of descriptions predicates and values """
    return( get_object_preds(g,id,DESCS))


def get_object_preds(g,id,predlist):
    """ get a dict of values for a list of PREDICATES"""
    labels = {}
    for lp in predlist:
        for lab in g.objects(predicate=lp, subject=id):
            labels[str(lp)] = lab
    return labels