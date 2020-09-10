import os
import re

from rdflib import RDF, RDFS, Graph, URIRef, PROF, Literal, OWL, BNode
from rdflib.namespace import split_uri, DCTERMS, SKOS, Namespace
from rdflib.plugins.sparql.datatypes import type_promotion, XSD_DTs
from rdflib.resource import Resource

SHACL = Namespace("http://www.w3.org/ns/shacl#")

known = { 'http://www.w3.org/2004/02/skos/core': 'skos',
          'http://purl.org/dc/terms' : 'dcterms'
          }

def set_known(uri,tok):
    known [uri] = tok

RDFS_TYPES = (RDFS.Class, RDF.Property)
RDFS_RELS = (RDFS.range, RDFS.subPropertyOf, RDFS.subClassOf)
OWL_TYPES = (OWL.Class,)
OWL_RELS = (OWL.DatatypeProperty,OWL.ObjectProperty)
LABELS = (DCTERMS.title, RDFS.label, SKOS.prefLabel)
DESCS = (DCTERMS.description, SKOS.definition, RDFS.comment )

def split_ns_uri(uri):
    """ Get a base uri  from a namespace - returning original uri if appropriate"""
    if uri[:-1] in '/#' :
        return uri[0:-1]
    return uri

def get_filebase(path):
    """ get the base of a filename from a path """
    return os.path.basename(path).rsplit("/", 1)[-1].rsplit(".")[0]

def get_objs_per_namespace(g, ontid, typesfilter=RDFS_TYPES+OWL_TYPES, relsfilter=RDFS_RELS+OWL_RELS ):
    """ return a dict with a dict of objects and types per namespace in graph
    :param g: Graph
    :return: Dict of { ns , Dict of {object,type} }
    """
    res = {}
    decs = set(())

    ont_ns = split_ns_uri(ontid)

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
            if split_ns_uri(ns) == ont_ns:
                ns = str(s)
            if ns not in res:
                res[ns] = {}
            if type or str(s) not in res[ns]:
                res[ns][str(s)] = type
    return res

def is_class(objtype):
    """ return true if the type is a Class object"""
    return objtype in ( RDFS.Class, OWL.Class)

def gettype(ontscope, prop):
    """get a property type

    looks at the declared range - or walks subProperty hierarchy looking for one
    :param ontscope: Ontology graph to use
    :param importclosure: imported ontologies to search if not found
    :param prop: property to locate
    :return: RDF IRI node with property range"""
    proptype = None
    propfocus = prop
    visited = set()
    while not proptype and propfocus :
        visited.add(propfocus)
        proptype = ontscope.value(prop, RDFS.range)
        if not proptype:
            # TODO - do we need to handle multiple superProperties?
            for sp in ontscope.objects(subject=propfocus, predicate=RDFS.subPropertyOf):
                propfocus = sp

            if propfocus in visited:
                return None
                # raise RecursionError ("Property %s already visited while finding superProperties" % (propfocus,) )

    return proptype

def get_basetype(ontscope,c):
    """ Get the underlying XSD type if available - else return None"""
    # loop TODO: anti-recursion checking
    basetype = type_promotion(c,c)
    if basetype in XSD_DTs:
        return basetype
    else:
        sup = ontscope.value(subject=c, predicate=RDFS.subClassOf)
        if sup:
            basetype = get_basetype(ontscope,sup)
            if basetype in XSD_DTs:
                return basetype
    return None


def get_objectprops(g):
    found = set()
    for op in g.subjects(predicate=RDF.type, object=OWL.ObjectProperty):
        found.add(set)
        yield op
    for op in g.subjects(predicate=RDF.type, object=RDF.Property):
        if op in found:
            continue
        ptype = gettype(g,op)
        if is_class(ptype):
            yield op
        continue

def get_dataprops(g):
    found = set()
    for op in g.subjects(predicate=RDF.type, object=OWL.DatatypeProperty):
        found.add(set)
        yield op
    for op in g.subjects(predicate=RDF.type, object=RDF.Property):
        if op in found:
            continue
        ptype = gettype(g,op)
        if not is_class(ptype):
            yield op
        continue



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
    """ returns a graph of objects from g in a namespace, with properties, including blank node contents

    if objlist is provided then all objects in list will be used, otherwise all objects will be scanned with get_obj_by_ns()
    :param g: source graph
    :param ns: namespace to extract (string)
    :param objlist: list of objects to extract
    """
    newg = Graph()
    newg.bind('owl',OWL)
    nsprefixes = {}
    for pre, bns in g.namespaces():
        nsprefixes[str(bns)] = pre

    if not objlist:
        objlist = []
        obsperns = get_objs_per_namespace(g,ns)
        for fullns in [ns, ns+'#', ns+'/']:
            if fullns in  obsperns.keys():
                objlist =obsperns[fullns].keys()
                newg.bind(nsprefixes[fullns], fullns)
                break

    if not objlist :
        return None

    o: object
    for o in objlist:
        for p, v in g.predicate_objects(URIRef(o)):
            add_nested(newg,g,((URIRef(o), p, v)))


    return newg

def add_nested(target,source,triple):
    """ add a value, and recursively add nested bnodes"""
    target.add(triple)
    n,p,o = triple
    if type(o) == BNode:
        for bp, bv in source.predicate_objects(o):
            add_nested(target,source, (o, bp, bv))


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

def classobjs(ont):
    """return a list of all objects that can be inferred to be an OWL or RDFS Class"""
    return list ( [ c for c in ont.subjects(predicate=RDF.type, object=OWL.Class)  if type(c) != BNode ]) + \
        list ( [ c for c in ont.subjects(predicate=RDF.type, object=RDFS.Class)  if type(c) != BNode ]) + \
        list( [ c for c in ont.subjects(predicate=RDFS.subClassOf) if type(c) != BNode ])


def getdeftoken(g,uri,qualify=True):
    """return a token form of a URI"""
    if qualify:
        try:
            return  Resource(g,URIRef(str(uri))).qname()
        except:
            return "dummy"
    else:
        return getonttoken(str(uri))