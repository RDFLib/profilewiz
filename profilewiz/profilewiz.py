import argparse
import errno
import json
import os
import re
import sys
import pylode
from prompt_toolkit import prompt
from rdflib import *
from rdflib.compare import *
from rdflib.namespace import RDF, RDFS, OWL
from rdflib.namespace import split_uri
from rdflib.util import guess_format

from ProfilesGraph import ProfilesGraph

IGNORE=( str(RDF.uri)[:-1] ,   str(RDFS.uri)[:-1] ,  str(OWL.uri)[:-1] , 'http://www.w3.org/2001/XMLSchema'  )

RDFS_TYPES=(RDFS.Class, RDF.Property)
RDFS_RELS=(RDFS.range, RDFS.subPropertyOf, RDFS.subClassOf)
OWL_TYPES=(OWL.Class,)
OWL_RELS=(OWL.DatatypeProperty,OWL.ObjectProperty)
LABELS = ( DCTERMS.title, RDFS.label, SKOS.prefLabel)
DESCS = (DCTERMS.description, SKOS.definition, RDFS.comment )
JSONLD_URI = URIRef('http://www.opengis.net/def/metamodel/profiles/json_ld_context')

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

known = { 'http://www.w3.org/2004/02/skos/core': 'skos',
          'http://purl.org/dc/terms' : 'dcterms'
          }

def getonttoken(url):
    """returns a candidate token from a URL

    for making filenames from the last part of an URI path before file extensions and queries """
    if url in known :
        return known[url]
    return re.sub("^[^\?]*/([a-zA-Z][^/?#]*).*$", r"\1", url)


def check_file_ok(base):
    """ check if a file name for a resource is acceptable"""
    if re.findall(r'[^A-Za-z0-9_]',base):
        return False,"Non alphanumeric characters in filename"
#    if os.path.exists( os.path.join('cache',base+'.ttl')):
#        return False,"Cached file of that name exists"
    else:
        return True,""


def safe_prompt(msg, default, checkfunc=None):
    """Get a valid response from a user , with a default value and a validation checker"""
    val = prompt( msg + '[' + default+ ']')
    if not val or val == default :
        return default
    elif checkfunc:
        valid,errmsg = checkfunc(val)
        if valid:
            return val
        else:
            return safe_prompt( errmsg + ' - try again', default, checkfunc=check_file_ok)
    else:
        return val


def cache_name(filebase):
    """ return name of file in cache

    (abstracted to allow smarter options for cache configuration in future)
    """
    return "cache/%s.ttl" % (filebase,)



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
        if ont in profiles.loadedowl:
            if profiles.loadedowl[ont]:
                ic += profiles.loadedowl[ont]
        else:
            ontg,filebase,fileloc = locate_ont(ont,options)
            if ontg:
                ic += ontg
            # if exists but is None then will be skipped
            profiles.loadedowl[ont] = ontg
            profiles.graph.add( (URIRef(ont), RDF.type, PROF.Profile ))
            profiles.addResource(URIRef(ont), Literal(fileloc) , "Cached OWL copy", role=PROF.cachedCopy , conformsTo=OWL.Ontology, format='text/turtle')

    return ic

def locate_ont(onturi, options):
    """ access cache or remote version of ontology

    With user interaction and defaults specified in options.
    Has side effect of updating cache.
    """

    loc = profiles.getLocal(onturi)
    if loc:
        filebase = getonttoken(loc)
    else:
        filebase = getonttoken(onturi)
        loc = cache_name(filebase)

    if not os.path.exists(loc) and options.ask:
        filebase = safe_prompt("Choose filename for local copy of ontology for %s" % (onturi,), filebase,
                               checkfunc=check_file_ok)
    try:
        ontg = Graph().parse(source=loc,format='ttl')
        print("Loaded %s from %s" % (onturi, loc))
    except:
        try:
            # ic.parse(source=ont, publicID=ont)
            if options.ask:
                fetchfrom = safe_prompt("URL to fetch ", onturi)
            else:
                fetchfrom = onturi
            ontg = Graph().parse(source=fetchfrom)
            ontg.serialize(destination=cache_name(filebase), format="ttl")
        except:
            profiles.loadedowl[onturi] = None
            print("failed to access or parse %s " % (onturi,))
            return None,None
    return ontg,filebase,loc


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

    for ns in IGNORE:
        try:
            ont_list.remove(ns)
        except:
            continue

    importclosure = get_graphs_by_ids(ont_list, options)
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



def  init_lib_if_absent( filename):
    if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

        #profiles.graph.serialize(dest=filename, format="turtle")


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

def make_context(ontid, ont, importclosure, usedns, q, imported={}):
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


# global profiles model
# this will be incrementally augmented from initial profile configuration and subsequent identification of profiles
profiles = ProfilesGraph()
# Current ontology describes as a profile - assumption is we'll want individual profile description artefacts


def __main__():
    parser = argparse.ArgumentParser(
        description="Create JSON context, schema and other views of an ontology"
    )
    parser.add_argument(
        "-o",
        "--output",
        nargs="?",
        type=argparse.FileType("a+"),
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
        "-c",
        "--choose-class",
        dest="choose_class",
        action="store_true",
        help="Choose a main Class object to create structural schema. Properties defined but not used are assumed to be allowable properties of main Class",
    )
    parser.add_argument(
        "-ho",
        "--html_owl",
        dest="html_owl",
        action="store_true",
        help="If set generate HTML for output OWL file, if present then do not perform analysis functions.",
    )
    parser.add_argument(
        "-hp",
        "--html_prof",
        dest="html_prof",
        action="store_true",
        help="If set generate HTML for output Profile description, if present then do not perform analysis functions.",
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
        "-a",
        "--ask",
        dest="ask",
        default=False,
        action="store_true",
        help="Ask for filenames and URI locations for imports not present in lib or cache",
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
    owl = output_file_base + ".ttl"
    prof = output_file_base + "_prof.ttl"
    css_found = os.path.exists("style.css")

    if not args.html_owl and not args.html_prof :
        # dont suppress analysis and generation phases
        if args.p:
            for p in [x for sx in args.p for x in sx]:
                profiles.parse(p, format=guess_format(p.name))
        if not os.path.exists('cache'):
            os.makedirs('cache')
        if args.init_lib:
            init_lib_if_absent(args.init_lib)
        ontid, ont, importclosure, dedupgraph, used_namespaces = get_graphs(args.input, args)

        curprofile = ProfilesGraph(id=ontid,
                                   labels=get_object_labels(ont, ontid),
                                   descriptions=get_object_descs(ont, ontid),
                                   meta={DCTERMS.source: args.input.name,
                                         SKOS.historyNote: "Ontology profile normalised using ProfileWiz"})
        if args.output.name == "<stdout>":
            print(dedupgraph.serialize(format="turtle"))
        else:
            dedupgraph.serialize(destination=args.output.name, format="turtle")
            curprofile.addResource(ontid, args.output.name, "Normalised OWL with imports" , role=PROF.vocabulary, conformsTo=OWL,
                                   format='text/turtle')
        if output_file_base != "<stdout>":
            with open(output_file_base + "_flat.jsonld", "w") as outfile:
                json.dump(make_context(ontid,ont, importclosure, used_namespaces, args.q), outfile, indent=4)
                curprofile.addResource(ontid, output_file_base + "_flat.jsonld", "Flattened JSON-LD context" , role=PROF.contextflat,
                                       conformsTo=JSONLD_URI, format='application/ld+json')

            with open(output_file_base + ".jsonld", "w") as outfile:
                json.dump(make_context(ontid,dedupgraph, importclosure, used_namespaces, args.q), outfile, indent=4)
                curprofile.addResource(ontid, output_file_base + ".jsonld", "JSON-LD Context", role=PROF.context, conformsTo=JSONLD_URI,
                                       format='application/ld+json')
        curprofile.addResource(ontid, output_file_base + "_prof.ttl", "Profile description including links to representations", role=PROF.profile, conformsTo=PROF,
                               format='text/turtle')


        curprofile.addResource(ontid, output_file_base + ".html",
                               "OWL documentation as HTML", role=PROF.profile,
                               conformsTo=PROF,
                               format='text/html')
        curprofile.addResource(ontid, output_file_base + "_prof.html",
                               "Profile description as HTML", role=PROF.profile,
                               conformsTo=PROF,
                               format='text/html')
        #serialise in advance so we can generate HTML view including links to HTML view...
        curprofile.graph.serialize(destination=output_file_base + "_prof.ttl", format="ttl")

    if not os.path.exists(prof):
        raise ("HTML generation mode requires TTL profile file %s available" % (prof,))
    with ( open(output_file_base + "_prof.html", "w") ) as htmlfile :
        html = pylode.MakeDocco(
input_data_file=prof,     outputformat="html",   profile="prof",     exclude_css=css_found ).document()
        htmlfile.write(html)

    if not os.path.exists(owl):
        raise ("HTML generation mode requires TTL output file %s available" % (owl,) )
    with (open(output_file_base + ".html", "w")) as htmlfile:
        html = pylode.MakeDocco(
            input_data_file=owl, outputformat="html", profile="ontdoc", exclude_css=css_found).document()
        htmlfile.write(html)


    if args.init_lib:
        if not os.path.exists(args.init_lib):
            profiles.graph.serialize(destination=args.init_lib, format="ttl")
    else:
        profiles.graph.serialize(destination="cache/profiles_cat.ttl", format="ttl")


__main__()
