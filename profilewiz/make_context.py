from .utils import gettype, classobjs, get_objectprops, get_dataprops, shortforms


def make_context(ontid, ont, importclosure, usedns, q, profiles=None, flat=True):
    """ make a JSON Context from objects (in a given namespace)- using imports if relevant

    Parameters
    ----------
    q
    importclosure
    ont
    ontid
    usedns
    profiles
    flat: boolean - force all elements to be included instead of context
    """
    print(q)

    context = {"@id": ontid, "@context": []}
    print(ontid)

    #localcontext = {"@vocab": ontid}
    localcontext = {}

    nsmap = {}
    for ns in ont.namespace_manager.namespaces():
        if not ns[0]:
            continue
        nsmap[str(ns[1])] = str(ns[0])

    for i, ns in enumerate(usedns.keys()):
        if profiles and not flat and ns != str(ontid):
            # check if an artefact is specified in the profile catalog
            # - otherwise we are (for now) relying on the namespace to behave nicely and return a jsonld context.
            ctx = profiles.getJSONcontext(ns)
            if ctx:
                context["@context"].insert(i, ctx)
            else:
                # context["@context"].insert(i,ns)
                print('Cannot locate jsonld context for %s' % ns)
        try:
            localcontext[nsmap[usedns[ns]]] = usedns[ns]
        except KeyError:
            pass

    for defclass in classobjs(ont):
        token, uri = shortforms(defclass, ont, q)
        if flat or uri == str(ontid):
            localcontext[token] = {"@id": uri}

    for objprop in get_objectprops(ont):
        token, uri = shortforms(objprop, ont, q)
        if flat or uri == str(ontid):
            localcontext[token] = {"@id": uri, "@type": "@id"}

    for prop in get_dataprops(ont):
        token, uri = shortforms(prop, ont, q)
        if flat or uri == str(ontid):
            localcontext[token] = {"@id": uri}
            proptype = gettype(importclosure, prop)
            if proptype:
                ptoken, uri = shortforms(proptype, ont, q)
                localcontext[token]["@type"] = uri

    context["@context"].append(localcontext)
    return context
