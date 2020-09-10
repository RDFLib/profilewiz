import argparse
import errno
import json
import os
import re
from datetime import datetime

import pylode
from prompt_toolkit import prompt
from rdflib import *
from rdflib.compare import *
from rdflib.namespace import RDF, RDFS, OWL
from rdflib.util import guess_format

from .Frame import Frame, Frameset
from .ProfilesGraph import ProfilesGraph
from .make_context import make_context
from .make_jsonschema import make_schema
from .make_shacl import make_shacl
# from profilewiz import VERSION
from .references import JSONLD_URI, JSONSCHEMA_URI

from .utils import get_objs_per_namespace, getonttoken, get_ont, extract_objs_in_ns, \
    get_object_labels, get_object_descs, is_class, get_filebase, set_known, add_nested, gettype, SHACL

VERSION = "0.1.4"

IGNORE = (str(RDF.uri)[:-1], str(RDFS.uri)[:-1], str(OWL.uri)[:-1], 'http://www.w3.org/2001/XMLSchema')


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

    Parameters
    ----------
    filebase : string
    """
    return "cache/%s.ttl" % (filebase,)


def provenate(g, obj, activity_desc="ProfileWiz", source=None):
    """ Add profilewiz provenance information to the object in the graph g"""
    g.bind("dcterms", DCTERMS)
    g.bind("prov", PROV)
    g.bind("owl", OWL)
    anode = BNode()
    agent = BNode()
    g.add((obj, PROV.wasGeneratedBy, anode))
    g.add((obj, RDF.type, PROV.Entity))
    g.add((agent, RDF.type, PROV.Agent))
    g.add((agent, RDFS.label, Literal("ProfileWiz " + VERSION)))
    g.add((anode, RDF.type, PROV.Activity))
    g.add((anode, PROV.wasAssociatedWith, agent))
    g.add((anode, RDFS.label, Literal(activity_desc)))
    g.add((anode, PROV.endedAtTime, Literal(datetime.today().isoformat(), datatype=XSD.date)))
    if source:
        snode = BNode()
        g.add((obj, PROV.wasDerivedFrom, snode))
        g.add((snode, RDF.type, PROV.Entity))
        g.add((snode, RDFS.label, Literal(os.path.abspath(source))))


def locate_ont(onturi, sourcegraph, source, options):
    """ access cache or remote version of ontology

    With user interaction and defaults specified in options.
    Has side effect of updating cache.

    if options.extract then if the ontology cannot be found the elements in the namespace will be added to the cache.
    if options.extend then options.extract behaviour and matching elements from the input ontology will be added to the existing cached copy.

    Parameters
    ----------
    source
    onturi
    sourcegraph
    options
    """

    loc, format = profiles.getLocal(onturi)
    if loc:
        filebase = getonttoken(loc)
    else:
        filebase = getonttoken(onturi)
        format = 'text/turtle'
        loc = cache_name(filebase)

    ontg = Graph()

    if not os.path.exists(loc) and options.ask:
        filebase = safe_prompt("Choose filename for local copy of ontology for %s" % (onturi,), filebase,
                               checkfunc=check_file_ok)
    try:
        ontg.parse(source=loc, format=format)
        print("Loaded %s from %s" % (onturi, loc))
    except:
        try:
            # ic.parse(source=ont, publicID=ont)
            while True:
                if options.ask:
                    fetchfrom = safe_prompt("URL to fetch (or Y to create, S to skip) ", onturi)
                else:
                    fetchfrom = onturi
                if options.extract or fetchfrom == 'Y':
                    ontg = extract_objs_in_ns(sourcegraph, onturi, objlist=None)
                    ontu = URIRef(onturi)
                    ontg.add((ontu, RDF.type, OWL.Ontology))
                    provenate(ontg, ontu, 'ProfileWiz: extraction of used terms from unavailable namespace',
                              source=source)
                    filebase = get_filebase(source) + "_" + filebase
                    storeat = os.path.join('extracted', filebase + ".ttl")
                    break
                elif fetchfrom != 'S':
                    ontg.parse(source=fetchfrom, format=guess_format(fetchfrom))
                    provenate(ontg, URIRef(onturi), "ProfileWiz: cached copy", source=fetchfrom)
                    storeat = cache_name(filebase)
                    break
                else:
                    raise
            ontg.serialize(destination=storeat, format="ttl")
        except:
            profiles.loadedowl[onturi] = None
            print("failed to access or parse %s " % (onturi,))
            return None, None, None

    set_known(onturi, filebase)

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


def get_graphs(input, ont, ont_id, curprofile, options):
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
    curprofile profile model of current ontology
    options  from parseargs

    Returns
    -------
    tuple ( ontology id, original ont( Graph), importclosure (Conjunctive Graph),  minimal_ont (Graph), maximal_ont (Graph), frames,  ontnamespacemap (dict) , frames (dict)
    """

    maximal_ont = Graph()

    obj_by_ns = get_objs_per_namespace(ont, str(ont_id))

    ont_list = list(ns2ontid(obj_by_ns.keys()))
    ont_ns_map = dict(zip(ont_list, obj_by_ns.keys()))

    # list of Class frames
    frameset = Frameset()
    try:
        ont_list.remove(str(ont_id))
    except:
        pass

    for ns in IGNORE:
        try:
            ont_list.remove(ns)
        except:
            continue

    token = get_filebase(input)

    # get base ontologies for namespaces referenced - as extracting (if requested) a local version if unavailable .
    importclosure = get_graphs_by_ids(ont_list, ont, input, options)

    # diff with input
    in_both, cleanont, in_second = graph_diff(ont, importclosure)

    for pre, ns in ont.namespaces():
        cleanont.bind(pre, ns)
        maximal_ont.bind(pre, ns)

    try:
        profilelib = ",".join(  [x.name for x in [ f[i] for i,f in enumerate(options.p) ] ] )
    except:
        profilelib = " none"
    provenate(cleanont, ont_id, 'ProfileWiz: Normalisation (source = %s, force_local=%s, profile libs : %s) ' % ( input, options.force_relative, profilelib ),
              source=input)

    # work through objects referenced from foreign namespaces
    used_obj_by_ns = get_objs_per_namespace(in_both, str(ont_id))
    for ns in ns2ontid(used_obj_by_ns.keys()):
        cleanont.add((ont_id, OWL.imports, URIRef(ns)))
        # create separate intermediate profile objects for all imported ontologies

        # directly profile imported ontology
        if options.extract:
            prof = URIRef(str(ont_id) + "_profile4" + getonttoken(ns))
            profiles.graph.add((prof, PROF.isProfileOf, URIRef(ns)))
            profiles.graph.add((prof, RDF.type, PROF.Profile))
        else:
            prof = URIRef(ns)
        for g in [cleanont, curprofile.graph, profiles.graph]:
            g.add((ont_id, PROF.isProfileOf, prof))
            if options.extract:
                g.add((ont_id, PROF.isTransitiveProfileOf, URIRef(ns)))

    # extend to create a flat version with full details of all objects specified
    maximal_ont += cleanont
    fullclosure = importclosure + cleanont
    # look through Class and Property declarations in original ontology
    # for efficiency roll in logic to detect declarations and restrictions
    for ns, objdict in obj_by_ns.items():
        for obj, objtype in objdict.items():
            curframe = None
            if is_class(objtype):
                curframe = frameset.framefor(obj)
                # find properties with a declared domain or domainIncludes
                for p in fullclosure.subjects(predicate=RDFS.domain, object=URIRef(obj)):
                    curframe.update(p)
                    ptype = gettype(fullclosure,p)


            for p, o in fullclosure.predicate_objects(subject=URIRef(obj)):
                if type(o) == Literal and options.language != '*' and o.language not in [options.language, 'en', None]:
                    continue
                maximal_ont.add((URIRef(obj), p, o))

                # restrictions assumed to be in blank nodes and may be additive across multiple nodes or contained in
                # a single node.
                if not type(o) == BNode:
                    if p == RDFS.subClassOf:
                        if not curframe:
                            curframe = Frame(obj)
                        curframe.addSuper(o)
                        # build frames for superclass hierarchy
                        frameset.buildframe(o, fullclosure)
                else:  # a Bnode
                    onProp = None
                    maxCard = None
                    minCard = None
                    hasValue = None
                    valuesFrom = None
                    for bp, bo in fullclosure.predicate_objects(subject=o):
                        add_nested(maximal_ont,fullclosure,((o, bp, bo)))
                        if p == RDFS.subClassOf:
                            if bp == OWL.onProperty:
                                onProp = bo
                            elif bp == OWL.hasValue:
                                hasValue = bo
                            elif bp == OWL.allValuesFrom:
                                valuesFrom = bo
                            else:
                                if bp == OWL.cardinality or bp == OWL.maxCardinality:
                                    maxCard = int(bo)
                                if bp == OWL.cardinality or bp == OWL.minCardinality:
                                    minCard = int(bo)
                    if onProp:
                        if not curframe:
                            curframe = Frame(obj)
                        curframe.update(onProp, maxCard=maxCard, minCard=minCard, hasValue=hasValue,
                                        valuesFrom=valuesFrom)


            if curframe:
                frameset.storeframe(obj, curframe)

    return ( cleanont, maximal_ont, fullclosure, importclosure, frameset, ont_ns_map)


def init_lib_if_absent(filename):
    if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

        # profiles.graph.serialize(dest=filename, format="turtle")


def get_graphs_by_ids(implist, input_ont, source, options):
    """ get a conjunctive graph containing contents retrieved from a list of URIs

    has side effects of:
     - caching fetched graphs under cache/{token}.ttl where {token} is derived from last path element of the URI
     - setting profiles.loadedowl[{ont}] to either a parsed Graph or None - to indicate it was not found


    :param implist: List of ontology ids to aggregate
    :param input_ont: Original ontology - will be used as source for extracted ontologies if options.extract = true
    :source name of input source for provenance capture
    :return: aggregrate Graph of importlist
    """
    ic = Graph()
    for ont in implist:
        if ont in profiles.loadedowl:
            if profiles.loadedowl[ont]:
                ic += profiles.loadedowl[ont]
        else:
            ontg, filebase, fileloc = locate_ont(ont, input_ont, source, options)
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


def main():
    parser = argparse.ArgumentParser(
        description="Create JSON context, schema and other views of an ontology"
    )
    parser.add_argument(
        "-o",
        "--output",
        nargs="?",
        # type=argparse.FileType("a+"),
        default=None,
        help="output file",
    )
    parser.add_argument(
        "-n",
        "--normalise",
        action="store_true",
        help="Extract minimal and flattened profile from an ontology with local copies of externally defined definitions",
    )
    parser.add_argument(
        "-e",
        "--extract",
        action="store_true",
        help="Automatically extract objects from other namespaces into cached ontologies (can be specified per ontology in ask mode)",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Create all artefacts",
    )
    parser.add_argument(
        "-f",
        "--flat",
        action="store_true",
        help="Create artefacts for de-normalised (flat)",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Create json context (normalised and flattened) outputs",
    )
    parser.add_argument(
        "-s",
        "--shacl",
        action="store_true",
        help="Create SHACL outputs",
    )

    parser.add_argument(
        "-qb",
        "--qb",
        action="store_true",
        help="Create RDF-Datacube Data Structure Definition  template output",
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
        "-l",
        "--language",
        dest="language",
        default="en",
        help="Language for imported strings (default = en, * for all languages)",
    )
    parser.add_argument(
        "-ho",
        "--html_owl",
        dest="html_owl",
        action="store_true",
        help="If set generate HTML for target OWL file (output file if --normalise mode, otherwise input file",
    )
    parser.add_argument(
        "-hp",
        "--html_prof",
        dest="html_prof",
        action="store_true",
        help="If set generate HTML for output Profile description",
    )
    parser.add_argument(
        "-x",
        "--xml",
        dest="xml",
        action="store_true",
        help="Create RDF/XML versions of all RDF forms (-all will produce TTL only)>",
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
        "-u",
        "--ask-user",
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
        # type=argparse.FileType("r"),
        nargs="+",
        help="input file(s) containing ontology in TTL format",
    )

    args = parser.parse_args()
    output = args.output

    if args.normalise:
        if args.p:
            for p in [x for sx in args.p for x in sx]:
                profiles.parse(p, format=guess_format(p.name))
        if not os.path.exists('cache'):
            os.makedirs('cache')
        with open('cache/README.txt', "w") as rm:
            rm.write(
                "cached ontology resources loaded from imports and namespace dereferencing")
        if not os.path.exists('extracted'):
            os.makedirs('extracted')
            with open('extracted/README.txt', "w") as rm:
                rm.write(
                    "Definitions extracted per namespace from profiled ontologies where configured library, imports and namespaces cannot be used to locate ontology resource.")
        if args.init_lib:
            init_lib_if_absent(args.init_lib)

    for files in args.input:
        if '*' in files:
            import glob
            for f in glob.glob(files):
                if not output:
                    args.output = os.path.basename(f)
                process(f, args)
        else:
            if not output:
                args.output = os.path.basename(files)
            process(files, args)


def process(name, args):
    """ Process an ontology file

    Generates a set of output files with default extended filenames based on input file or designated output file name
    """
    print("Profiling %s to %s\n" % ((name, args.output)))
    if args.output:
        output_file_base = get_filebase(args.output)
    else:
        output_file_base = get_filebase(name)
    # Process known resources and intentions from the profile catalog list, before
    owl = output_file_base + ".ttl"
    prof = output_file_base + "_prof.ttl"
    css_found = os.path.exists("style.css")
    dedupgraph = None
    ont = None
    maximal_ont = None
    curprofile = None
    ont = Graph().parse(name, format="ttl")
    ontid = get_ont(ont)

    if args.all or args.normalise:
        # dont suppress analysis and generation phases

        curprofile = ProfilesGraph(id=ontid,
                                   labels=get_object_labels(ont, ontid),
                                   descriptions=get_object_descs(ont, ontid),
                                   meta={PROV.wasDerivedFrom: name,
                                         SKOS.historyNote: "Ontology profile normalised using ProfileWiz"})
        curprofile.addResource(ontid, name, "Original Source OWL model",
                               desc="Source OWL model used to derive normalised profile views.",
                               role=PROF.source,
                               conformsTo=OWL,
                               format='text/turtle')
        try:
            dedupgraph, maximal_ont, fullclosure, importclosure, frames, used_namespaces = get_graphs(name, ont, ontid, curprofile,
                                                                                         args)
        except Exception as e:
            import sys
            import traceback
            traceback.print_exc(file=sys.stdout)
            traceback.print_exc(limit=1, file=sys.stdout)
            print("Failed to process graph %s : \n %s" % (name, e))
            return

        formats = {'ttl': 'text/turtle'}
        if args.xml:
            formats['xml'] = 'application/xml+rdf'
        if args.json:
            formats['jsonld'] = 'application/ld+json'
        if args.output == "-":
            print(dedupgraph.serialize(format="turtle"))
        else:
            for fmt,mime in formats.items():
                dedupgraph.serialize(destination=output_file_base+ "." + fmt, format='json-ld' if fmt == 'jsonld' else fmt)
                curprofile.addResource(ontid, output_file_base+ "." + fmt, "Normalised OWL with imports",
                                       desc="This is an OWL file with imports for ontologies containing all object definitions, but with only statements not present in imports",
                                       role=PROF.vocabulary,
                                       conformsTo=OWL,
                                       format=mime)
                if args.all or args.flat:
                    maximal_ont.serialize(destination=output_file_base + "_flat." + fmt, format=fmt)
                    curprofile.addResource(ontid, output_file_base + "_flat." + fmt,
                                           "OWL with definition details from imports",
                                           role=PROF.vocabulary,
                                           conformsTo=OWL,
                                           desc="This is a OWL file containing all the properties of objects used by the profile in a single (flat) denormalised file. This may be augmented in future with RDF* or reified statements with the provenance of each statement if required.",
                                           format=mime)
            if args.all or args.json:
                with open(output_file_base + "_context_flat.jsonld", "w") as outfile:
                    json.dump(make_context(ontid, maximal_ont, fullclosure, used_namespaces, args.q), outfile, indent=4)
                    curprofile.addResource(ontid, output_file_base + "_context_flat.jsonld", "Flattened JSON-LD context",
                                           role=PROF.contextflat,
                                           conformsTo=JSONLD_URI, format='application/ld+json')
            if args.all or args.json:
                with open(output_file_base + "_context.jsonld", "w") as outfile:
                    json.dump(make_context(ontid, dedupgraph, fullclosure, used_namespaces, args.q), outfile,
                              indent=4)
                    curprofile.addResource(ontid, output_file_base + "_context.jsonld", "JSON-LD Context", role=PROF.context,
                                           conformsTo=JSONLD_URI,
                                           format='application/ld+json')
            if args.all or args.json:
                with open(output_file_base + ".json", "w") as outfile:
                    json.dump(make_schema(ontid, dedupgraph,  args.q, frames), outfile, indent=4)
                    curprofile.addResource(ontid, output_file_base + ".json", "JSON Schema", role=PROF.schema,
                                           conformsTo=JSONSCHEMA_URI,
                                           format='application/json')

            if args.all or args.html_owl:
                with (open(output_file_base + "_source.html", "w", encoding='utf-8')) as htmlfile:
                    html = pylode.MakeDocco(
                        input_graph=ont, outputformat="html", profile="ontdoc", exclude_css=css_found).document()
                    htmlfile.write(html)
                    curprofile.addResource(ontid, output_file_base + "_source.html",
                                           "Profile description as HTML", role=PROF.profile,
                                           conformsTo=PROF,
                                           desc="Original source OWL file as HTML - for comparison and review purposes",
                                           format='text/html')

    # ok fall into artefact generation options - using input file if we havent created a normalised profile...

    if not curprofile:
        if not os.path.exists(prof):
            raise FileNotFoundError("Artefact generation modes without --normalise requires TTL profile file %s available" % (prof,))
        curprofile = ProfilesGraph()
        curprofile.parse(source=prof, format='turtle')

    if not os.path.exists(owl):
        raise FileNotFoundError("HTML generation mode requires TTL output file %s available" % (owl,))
    if not maximal_ont:
        maximal_ont = Graph().parse(source=owl, format='turtle')

    if args.all or args.shacl:
        with (open(output_file_base + "_flat_shacl.ttl", "w", encoding='utf-8')) as file:
            shacl = make_shacl(ontid, maximal_ont, imported={},
                               subs={'https://astrea.linkeddata.es/shapes': ontid + "_shapes",
                                     'http://schema.org/': 'https://schema.org/'})
            file.write(shacl)
            curprofile.addResource(ontid, output_file_base + "_flat_shacl.ttl",
                                   "SHACL constraints for profile",
                                   desc="SHACL validation constraints for all declarations relevant to profile including imports",
                                   role=PROF.validation,
                                   conformsTo=SHACL,
                                   format='text/turtle')
        with (open(output_file_base + "_shacl.ttl", "w", encoding='utf-8')) as file:
            shacl = make_shacl(ontid, dedupgraph, imported={},
                               subs={'https://astrea.linkeddata.es/shapes': ontid + "_shapes",
                                     'http://schema.org/': 'https://schema.org/'})
            file.write(shacl)
            curprofile.addResource(ontid, output_file_base + "_shacl.ttl",
                                   "SHACL for minimal profile",
                                   desc="SHACL validation constraints for profile specific declarations",
                                   role=PROF.validation,
                                   conformsTo=SHACL,
                                   format='text/turtle')

    if args.all or args.html_owl:
        docgraph = maximal_ont
        curprofile.addResource(ontid, output_file_base + ".html",
                               "OWL documentation as HTML",
                               desc="Based on the OWL flat view of the profile, a HTML rendering of key elements of the model.",
                               role=PROF.profile,
                               conformsTo=PROF,
                               format='text/html')
        with (open(output_file_base + ".html", "w", encoding='utf-8')) as htmlfile:
            html = pylode.MakeDocco(
                input_graph=docgraph, outputformat="html", profile="ontdoc", exclude_css=css_found).document()
            htmlfile.write(html)

    # serialise current profile last - so it captures all formats generated
    if args.all or args.html_prof:
        curprofile.addResource(ontid, output_file_base + "_prof.html",
                               "Profile description as HTML", role=PROF.profile,
                               conformsTo=PROF,
                               desc="Overview of profile and available descriptive and implementation support resources",
                               format='text/html')
        with (open(output_file_base + "_prof.html", "w", encoding='utf-8')) as htmlfile:
            html = pylode.MakeDocco(
                input_graph=curprofile.graph, outputformat="html", profile="prof", exclude_css=css_found).document()
            htmlfile.write(html)
        # serialise in advance so we can generate HTML view including links to HTML view...
        curprofile.graph.serialize(destination=output_file_base + "_prof.ttl", format="ttl")

    if args.init_lib and not os.path.exists(args.init_lib):
            profiles.graph.serialize(destination=args.init_lib, format="ttl")
    else:
        profiles.graph.serialize(destination=output_file_base + "_tmp_profiles_cat.ttl", format="ttl")

if __name__ == '__main__':
    main()
