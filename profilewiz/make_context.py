import rdflib

from utils import gettype

def make_context(ontid, ont, importclosure, usedns, q,  imported={}):
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


    for defclass in list(ont.subjects(predicate=rdflib.RDF.type, object=rdflib.OWL.Class)) + list(ont.subjects(predicate=rdflib.RDFS.subClassOf)) :
        localcontext[
            ont.namespace_manager.compute_qname(defclass)[2]
            if q
            else defclass.n3(ont.namespace_manager)
        ] = {"@id": defclass.n3(ont.namespace_manager)}

    for objprop in ont.subjects(predicate=rdflib.RDF.type, object=rdflib.OWL.ObjectProperty):
        localcontext[
            ont.namespace_manager.compute_qname(objprop)[2]
            if q
            else objprop.n3(ont.namespace_manager)
        ] = {"@id": objprop.n3(ont.namespace_manager), "@type": "@id"}

    for prop in ont.subjects(predicate=rdflib.RDF.type, object=rdflib.OWL.DatatypeProperty):
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