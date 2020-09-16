import rdflib

from .utils import gettype, classobjs, get_objectprops, get_dataprops, shortforms


def make_context(ontid, ont, importclosure, usedns, q,  profiles=None):
    """ make a JSON Context from objects (in a given namespace)- using imports if relevant

    Parameters
    ----------
    profiles : ProfilesGraph
    """
    print(q)

    context = {}
    context["@id"] = ontid
    context["@context"] = []
    print(ontid)

    localcontext= { "@vocab" : ontid }

    nsmap= { }
    for ns in ont.namespace_manager.namespaces():
        if not ns[0]:
            continue
        nsmap[str(ns[1])  ] = str(ns[0])



    lastindex = 0
    for i,ns in enumerate(usedns.keys()):
        if profiles and ns != str(ontid) :
            # check if an artefact is specified in the profile catalog - otherwise we are (for now) relying on the namespace to behave nicely and return a jsonld context.
            ctx = profiles.getJSONcontext(ns)
            if ctx:
                context["@context"].insert(i, ctx )
            else:
                #context["@context"].insert(i,ns)
                print ( 'Cannot locate jsonld context for %s' % ns )
        try:
            localcontext[nsmap[usedns[ns]]] = usedns[ns]
        except:
            pass
        lastindex=i+1



    for defclass in classobjs(ont) :
        token,id = shortforms(defclass,ont,q)
        localcontext[ token] = {"@id": id }

    for objprop in get_objectprops(ont):
        token, id = shortforms(objprop, ont, q)
        localcontext[token] = {"@id": id, "@type": "@id"}

    for prop in get_dataprops(ont):
        token, id = shortforms(prop, ont, q)
        localcontext[token] = {"@id": id }
        proptype = gettype(importclosure, prop)
        if proptype:
            ptoken,id = shortforms(proptype, ont, q)
            localcontext[token]["@type"] = id

    context["@context"].append( localcontext )
    return context