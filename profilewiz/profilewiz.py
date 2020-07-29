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
from rdflib.util import guess_format

from ProfilesGraph import ProfilesGraph
from make_context import make_context
from utils import get_objs_per_namespace, getonttoken, get_ont, extract_objs_in_ns, \
    get_object_labels, get_object_descs, is_class

IGNORE = (str(RDF.uri)[:-1], str(RDFS.uri)[:-1], str(OWL.uri)[:-1], 'http://www.w3.org/2001/XMLSchema')

JSONLD_URI = URIRef('http://www.opengis.net/def/metamodel/profiles/json_ld_context')


def check_file_ok(base):
    """ check if a file name for a resource is acceptable"""
    if re.findall(r'[^A-Za-z0-9_]', base):
        return False, "Non alphanumeric characters in filename"
    #    if os.path.exists( os.path.join('cache',base+'.ttl')):
    #        return False,"Cached file of that name exists"
    else:
        return True, ""


def safe_prompt(msg, default, checkfunc=None):
    """Get a valid response from a user , with a default value and a validation checker"""
    val = prompt(msg + '[' + default + ']')
    if not val or val == default:
        return default
    elif checkfunc:
        valid, errmsg = checkfunc(val)
        if valid:
            return val
        else:
            return safe_prompt(errmsg + ' - try again', default, checkfunc=check_file_ok)
    else:
        return val


def cache_name(filebase):
    """ return name of file in cache

    (abstracted to allow smarter options for cache configuration in future)
    """
    return "cache/%s.ttl" % (filebase,)


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
        ontg = Graph().parse(source=loc, format='ttl')
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
            return None, None, None

    return ontg, filebase, loc


def ns2ontid(nsset):
    """ Yields a list of namespaces as ontology ids by removing trailing / or #"""
    for ns in nsset:
        nss = ns[:-1]
        nse = ns[-1:]
        if nse in ("/", "#"):
            yield nss
        else:
            yield ns


def get_graphs(input, options):
    """ Get an ontology and all its explicit or implicit imports

    Get target ontology, identify all objects and a build a graph containing import for namespaces use

    - creates minimal (specific to profile) and maximal (all known from imports) graphs of properties of objects
    - creates "frame" (schema, shape ) view of Class objects using available clues:
        - availability of a schema definition resource in the profile catalog (JSON-schema, RDF-QB etc)
        - OWL restrictions
        - presence of property definitions in graph (if only one Class defined)

    Side-effects:
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
    tuple ( ontology id, original ont( Graph), importclosure (Conjunctive Graph),  minimal_ont (Graph), maximal_ont (Graph), frames,  ontnamespacemap (dict) , frames (dict)
    """

    ont = Graph().parse(input, format="ttl")
    maximal_ont = Graph()
    ont_id = get_ont(ont)
    obj_by_ns = get_objs_per_namespace(ont, str(ont_id))

    ont_list = list(ns2ontid(obj_by_ns.keys()))
    ont_ns_map = dict(zip(ont_list, obj_by_ns.keys()))

    # list of Class frames
    frames = {}
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

    in_both, cleanont, in_second = graph_diff( ont, importclosure)

    for pre, ns in ont.namespaces():
        cleanont.bind(pre, ns)
        maximal_ont.bind(pre, ns)

    used_obj_by_ns = get_objs_per_namespace(in_both, str(ont_id))
    for ns in ns2ontid(used_obj_by_ns.keys()):
        cleanont.add((ont_id, OWL.imports, URIRef(ns)))
        maximal_ont.add((ont_id, OWL.imports, URIRef(ns)))

    maximal_ont += cleanont
    for ns, objdict in obj_by_ns.items():
        for obj, objtype in objdict.items():
            for p, o in importclosure.predicate_objects(subject=URIRef(obj)):
                maximal_ont.add((URIRef(obj), p, o))
                if type(o) == BNode:
                    for bp,bo in importclosure.predicate_objects(subject=o):
                        maximal_ont.add( (o , bp, bo ))
            if is_class(objtype):
                print('make a frame for ', obj)

    return (ont_id, ont, importclosure, cleanont, maximal_ont, frames, ont_ns_map)


def init_lib_if_absent(filename):
    if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

        # profiles.graph.serialize(dest=filename, format="turtle")


def get_graphs_by_ids(implist, options):
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
            ontg, filebase, fileloc = locate_ont(ont, options)
            if ontg:
                ic += ontg
            # if exists but is None then will be skipped
            profiles.loadedowl[ont] = ontg
            profiles.graph.add((URIRef(ont), RDF.type, PROF.Profile))
            profiles.addResource(URIRef(ont), Literal(fileloc), "Cached OWL copy", role=PROF.cachedCopy,
                                 conformsTo=OWL.Ontology, format='text/turtle')

    return ic


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
    dedupgraph = None
    ont = None
    curprofile = None

    if not args.html_owl and not args.html_prof:
        # dont suppress analysis and generation phases
        if args.p:
            for p in [x for sx in args.p for x in sx]:
                profiles.parse(p, format=guess_format(p.name))
        if not os.path.exists('cache'):
            os.makedirs('cache')
        if args.init_lib:
            init_lib_if_absent(args.init_lib)
        ontid, ont, importclosure, dedupgraph, maximal_ont, frames, used_namespaces = get_graphs(args.input, args)

        curprofile = ProfilesGraph(id=ontid,
                                   labels=get_object_labels(ont, ontid),
                                   descriptions=get_object_descs(ont, ontid),
                                   meta={DCTERMS.source: args.input.name,
                                         SKOS.historyNote: "Ontology profile normalised using ProfileWiz"})
        if args.output.name == "<stdout>":
            print(dedupgraph.serialize(format="turtle"))
        else:
            dedupgraph.serialize(destination=args.output.name, format="turtle")
            curprofile.addResource(ontid, args.output.name, "Normalised OWL with imports", role=PROF.vocabulary,
                                   conformsTo=OWL,
                                   format='text/turtle')
            maximal_ont.serialize(destination=output_file_base + "_flat.ttl", format="turtle")
            curprofile.addResource(ontid, args.output.name, "OWL with definition details from imports", role=PROF.vocabulary,
                                   conformsTo=OWL,
                                   format='text/turtle')
            with open(output_file_base + "_flat.jsonld", "w") as outfile:
                json.dump(make_context(ontid, ont, importclosure, used_namespaces, args.q), outfile, indent=4)
                curprofile.addResource(ontid, output_file_base + "_flat.jsonld", "Flattened JSON-LD context",
                                       role=PROF.contextflat,
                                       conformsTo=JSONLD_URI, format='application/ld+json')

            with open(output_file_base + ".jsonld", "w") as outfile:
                json.dump(make_context(ontid, dedupgraph, importclosure, used_namespaces, args.q), outfile, indent=4)
                curprofile.addResource(ontid, output_file_base + ".jsonld", "JSON-LD Context", role=PROF.context,
                                       conformsTo=JSONLD_URI,
                                       format='application/ld+json')
        curprofile.addResource(ontid, output_file_base + "_prof.ttl",
                               "Profile description including links to representations", role=PROF.profile,
                               conformsTo=PROF,
                               format='text/turtle')

        curprofile.addResource(ontid, output_file_base + ".html",
                               "OWL documentation as HTML", role=PROF.profile,
                               conformsTo=PROF,
                               format='text/html')
        curprofile.addResource(ontid, output_file_base + "_prof.html",
                               "Profile description as HTML", role=PROF.profile,
                               conformsTo=PROF,
                               format='text/html')
        # serialise in advance so we can generate HTML view including links to HTML view...
        curprofile.graph.serialize(destination=output_file_base + "_prof.ttl", format="ttl")

    if not os.path.exists(prof):
        raise ("HTML generation mode requires TTL profile file %s available" % (prof,))
    if not curprofile:
        curprofile = ProfilesGraph()
        curprofile.parse(source=prof, format='turtle')

    with (open(output_file_base + "_prof.html", "w")) as htmlfile:
        html = pylode.MakeDocco(
            input_graph=curprofile.graph, outputformat="html", profile="prof", exclude_css=css_found).document()
        htmlfile.write(html)

    if not os.path.exists(owl):
        raise ("HTML generation mode requires TTL output file %s available" % (owl,))
    if not maximal_ont:
        maximal_ont = Graph().parse(source=owl, format='turtle')

    docgraph = maximal_ont
    with (open(output_file_base + ".html", "w")) as htmlfile:
        html = pylode.MakeDocco(
            input_graph=docgraph, outputformat="html", profile="ontdoc", exclude_css=css_found).document()
        htmlfile.write(html)

    if not ont:
        ont = Graph().parse(args.input, format="ttl")
    with (open(output_file_base + "_source.html", "w")) as htmlfile:
        html = pylode.MakeDocco(
            input_graph=ont, outputformat="html", profile="ontdoc", exclude_css=css_found).document()
        htmlfile.write(html)

    if args.init_lib:
        if not os.path.exists(args.init_lib):
            profiles.graph.serialize(destination=args.init_lib, format="ttl")
    else:
        profiles.graph.serialize(destination="cache/profiles_cat.ttl", format="ttl")


__main__()
