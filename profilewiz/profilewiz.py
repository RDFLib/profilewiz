import argparse
import json
import sys
import os
import re
from rdflib import *
from rdflib.compare import *
from rdflib.namespace import split_uri
from rdflib.util import guess_format
from urllib.parse import urlparse
from rdflib.namespace import RDF, RDFS, OWL, XSD

RDFS_TYPES=(RDFS.Class, RDF.Property)
RDFS_RELS=(RDFS.range, RDFS.subPropertyOf, RDFS.subClassOf)
OWL_TYPES=(OWL.Class,)
OWL_RELS=(OWL.DatatypeProperty,OWL.ObjectProperty)

def gettype(ontscope, importclosure, prop):
    """get a property type

    looks at the declared range - or walks subProperty hierarchy looking for one
    :param ontscope: Ontology graph to use
    :param importclosure: imported ontologies to search if not found
    :param prop: property to locate
    :return: RDF IRI node with property range"""
    proptype = ontscope.value(prop, RDFS.range)
    return proptype


def get_objs_per_namespace(g, ontid, typesfilter=RDFS_TYPES+OWL_TYPES, relsfilter=RDFS_RELS+OWL_RELS ):
    """ return a dict with a dict of objects and types per namespace in graph
    :param g: Graph
    :return: Dict of ns, Dict of {object,type}
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


def getonttoken(url):
    """returns a candidate token from a URL

    for making filenames from the last part of an URI path before file extensions and queries """

    return re.sub("^[^\?]*/([a-zA-Z][^/?#]*).*$", r"\1", url)


def get_graphs_by_ids(implist,options):
    """ get a conjunctive graph containing contents retrieved from a list of URIs

    has side effects of:
     - caching fetched graphs under cache/{token}.ttl where {token} is derived from last path element of the URI
     - setting profiles.loadedowl[{ont}] to either a parsed Graph or None - to indicate it was not found


    :param implist: List of ontology ids to aggregate
    :return: aggregrate Graph of importlist
    """
    ic = Graph()
    for ont in implist:
        filebase = getonttoken(ont)
        if ont in profiles.loadedowl:
            ic += profiles.loadedowl[ont]
        else:
            try:
                ontg = Graph().parse(source="cache/%s.ttl" % (filebase,) )
                print("Loaded %s from cache" % (ont,))
            except:
                try:
                   # ic.parse(source=ont, publicID=ont)
                    ontg = Graph().parse(source=ont)
                    ontg.serialize(destination="cache/%s.ttl" % (filebase,), format="ttl")
                except:
                    profiles.loadedowl[ont] = None
                    print("failed to access or parse %s " % (ont,))

            ic += ontg
            profiles.loadedowl[ont] = ontg
    return ic


def ns2ontid(nsset):
    """ Yields a list of namespaces as ontology ids by removing trailing / or #"""
    for ns in nsset:
        nss = ns[:-1]
        nse = ns[-1:]
        if nse in ("/", "#"):
            yield nss
        else:
            yield ns

def get_ont(graph):
    """ return URI of declared ontology in a graph """
    return graph.value(predicate=RDF.type, object=OWL.Ontology)

def get_graphs(input, options):
    """ Get an ontology and all its explicit or implicit imports

    Get target ontology and a graph containing imports,
    * using the singleton profiles catalog graph to find local copies of resources
    * asking (if in init_lib mode) for help to locate resources if resources not available
    * acquiring and caching (under ./cache/ by default) ontologies from imports or referenced namespaces
    * updating the specified profiles catalog to reference imports

    Parameters
    ----------
    input    input file
    options  from parseargs

    Returns
    -------
    tuple ( ont, ..)
    """

    ont = Graph().parse(input, format="ttl")
    ont_id = get_ont(ont)
    obj_by_ns = get_objs_per_namespace(ont, str(ont_id))

    ont_list = list(ns2ontid(obj_by_ns.keys()))
    ont_ns_map = dict(zip(ont_list, obj_by_ns.keys()))
    try:
        ont_list.remove(str(ont_id))
    except:
        pass

    importclosure = get_graphs_by_ids(ont_list,options)
    if False:
        # get unloaded ontology list
        for extra_ont in [x for x, g in profiles.loadedowl.items() if not g]:
            eg = extract_objs_in_ns(
                ont, extra_ont, objlist=obj_by_ns[ont_ns_map[extra_ont]].keys()
            )
            importclosure += eg
            eg.serialize(destination=getonttoken(extra_ont) + ".ttl", format="turtle")
            # profiles.addloadedowl[extra_ont] = eg

    in_both, cleanont, in_second = graph_diff(
      #  to_isomorphic(ont), to_isomorphic(importclosure)
    to_canonical_graph(ont),to_canonical_graph (importclosure)
    )
    for pre, ns in ont.namespaces():
        cleanont.bind(pre, ns)
    used_obj_by_ns = get_objs_per_namespace(in_both, str(ont_id))
    for ns in ns2ontid(used_obj_by_ns.keys()):
        cleanont.add((ont_id, OWL.imports, URIRef(ns)))
    return (ont_id, ont, importclosure, cleanont,ont_ns_map)


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

DEFAULT_NS = [ ('prof', 'http://www.w3.org/ns/dx/prof/' )]

class ProfilesGraph:
    """ A container for a map of known profiles and supporting resources """

    def __init__(self):
        self.graph = Graph()
        self.loadedowl = {}
        self.ldcontexts = {}
        for pre,ns in DEFAULT_NS :
            self.graph.namespace_manager.bind(pre,URIRef(ns))

    def parse(self, source, *args, **kwargs):
        self.graph.parse(source, *args, **kwargs)
        self.ldcontexts = self.getResourcesDict(
            "prof:schema", "<https://www.w3.org/TR/json-ld/>"
        )
        for p, ont in self.getResourcesDict("prof:vocabulary", "owl:").items():
            print("preloading ontology: ", p, " from ", ont)
            self.loadedowl[p] = Graph().parse(ont, format=guess_format(ont))

    def getResourcesDict(self, role, fmt):
        """ Get a dict resources for a given role and content type

        role = string URI - may use prof:X form
        fmt = string URI - may use prof:
        """
        res = {}
        qarts = """SELECT ?p ?c
               WHERE { 
                ?p prof:hasResource ?r .
                ?r prof:hasRole %s . 
                ?r dct:conformsTo %s .
                 ?r prof:hasArtifact ?c . 
                 } """ % (
            role,
            fmt,
        )
        arts = self.graph.query(qarts)
        for p, c in arts:
            res[str(p)] = str(c)
        return res


# global profiles model
# this will be incrementally augmented from initial profile configuration and subsequent identification of profiles
profiles = ProfilesGraph()

def  init_lib_if_absent( filename):
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

        profiles.graph.serialize(dest=filename, format="turtle")




def make_context(ont, importclosure, usedns, q, imported={}):
    """ make a JSON Context from objects (in a given namespace)- using imports if relevant"""
    print(q)

    context = {}
    context["@id"] = ontid
    context["@context"] = []
    print(ontid)

    nsmap= { }
    for ns in ont.namespace_manager.namespaces():
        nsmap[str(ns[1])] = str(ns[0])

    localcontext= {}

    lastindex = 0
    for i,ns in enumerate(usedns.keys()):
        context["@context"].insert(i,ns)
        try:
            localcontext[nsmap[usedns[ns]]] = usedns[ns]
        except:
            pass
        lastindex=i+1


    for defclass in list(ont.subjects(predicate=RDF.type, object=OWL.Class))+ list( ont.subjects(predicate=RDFS.subClassOf)) :
        localcontext[
            ont.namespace_manager.compute_qname(defclass)[2]
            if q
            else defclass.n3(ont.namespace_manager)
        ] = {"@id": defclass.n3(ont.namespace_manager)}

    for objprop in ont.subjects(predicate=RDF.type, object=OWL.ObjectProperty):
        localcontext[
            ont.namespace_manager.compute_qname(objprop)[2]
            if q
            else objprop.n3(ont.namespace_manager)
        ] = {"@id": objprop.n3(ont.namespace_manager), "@type": "@id"}

    for prop in ont.subjects(predicate=RDF.type, object=OWL.DatatypeProperty):
        pc = (
            prop.n3(ont.namespace_manager)
            if not q
            else ont.namespace_manager.compute_qname(prop)[2]
        )
        localcontext[pc] = {"@id": prop.n3(ont.namespace_manager)}
        proptype = gettype(ont, importclosure, prop)
        if proptype:
            localcontext[pc]["@type"] = proptype.n3(ont.namespace_manager)

    context["@context"].append( localcontext )
    return context


parser = argparse.ArgumentParser(
    description="Create JSON context, schema and other views of an ontology"
)

parser.add_argument(
    "-o",
    "--output",
    nargs="?",
    type=argparse.FileType("w"),
    default=sys.stdout,
    help="output file",
)
parser.add_argument(
    "-q",
    "--qnames_only",
    dest="q",
    action="store_true",
    help="use qnames only for JSON elements",
)
parser.add_argument(
    "-r",
    "--force_relative",
    dest="force_relative",
    action="store_true",
    help="use relative filenames and cached copies for imports",
)
parser.add_argument(
    "-p",
    "--profiles",
    dest="p",
    default=None,
    nargs="+",
    action="append",
    type=argparse.FileType("r"),
    help="file name or URL of profiles model with pre-configured resource locations",
)
parser.add_argument(
    "-i",
    "--init_lib",
    dest="init_lib",
    nargs="?",
    help="Initialise or update profile library and profile catalog with used namespaces using first named profile catalog"
)
parser.add_argument(
    "input",
    type=argparse.FileType("r"),
    default=sys.stdin,
    help="input file containing ontology in TTL format",
)

args = parser.parse_args()

input_file_base = args.input.name.rsplit("/", 1)[-1].rsplit(".")[0]
output_file_base = args.output.name.rsplit("/", 1)[-1].rsplit(".")[0]
# Process known resources and intentions from the profile catalog list, before
if args.p :
    for p in [x for sx in args.p for x in sx]:
        profiles.parse(p, format=guess_format(p.name))

if not os.path.exists('cache'):
    os.makedirs('cache')
if args.init_lib:
    init_lib_if_absent(args.init_lib)
ontid, ont, importclosure, dedupgraph, used_namespaces = get_graphs(args.input, args)
if args.output.name == "<stdout>":
    print(dedupgraph.serialize(format="turtle"))
else:
    dedupgraph.serialize(destination=args.output.name, format="turtle")
if output_file_base != "<stdout>":
    with open(output_file_base + "_flat.jsonld", "w") as outfile:
        json.dump(make_context(ont, importclosure, used_namespaces, args.q), outfile, indent=4)
    with open(output_file_base + ".jsonld", "w") as outfile:
        json.dump(make_context(dedupgraph, importclosure, used_namespaces, args.q), outfile, indent=4)
