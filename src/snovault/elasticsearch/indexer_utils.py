def find_uuids_for_indexing(indices, es, updated, renamed, log):
    from .create_mapping import index_settings
    SEARCH_MAX = 99999  # OutOfMemoryError if too high
    """
    Run a search to find uuids of objects with embedded uuids in updated
    or linked uuids in renamed. Only runs over the given indices.
    """
    invalidated = set()
    referencing = set()
    flush = False
    for es_index in indices:
        this_index_exists = es.indices.exists(index=es_index)
        if not this_index_exists:
            continue
        es.indices.refresh(index=es_index)
        res = es.search(index=es_index, size=SEARCH_MAX, body={
            'query': {
                'bool': {
                    'filter': {
                        'bool': {
                            'should': [
                                {
                                    'terms': {
                                        'embedded_uuids': list(updated),
                                        '_cache': False,
                                    },
                                },
                                {
                                    'terms': {
                                        'linked_uuids': list(renamed),
                                        '_cache': False,
                                    },
                                },
                            ],
                        },
                    },
                },
            },
            '_source': False,
        })
        log.debug("Found %s items of type %s for indexing" %
                 (str(res['hits']['total']), es_index))
        if res['hits']['total'] > SEARCH_MAX:
            referencing = list(all_uuids(request.registry))
            flush = True
            break
        else:
            found_uuids = {hit['_id'] for hit in res['hits']['hits']}
            referencing= referencing | found_uuids
    invalidated = referencing | updated
    return invalidated, referencing, flush


def get_uuids_for_types(registry, types=None):
    from snovault import COLLECTIONS
    """
    Generator function to return uuids for all the given types. If no
    types provided, uses all types.
    """
    # First index user and access_key so people can log in
    collections = registry[COLLECTIONS]
    initial = ['user', 'access_key']
    for collection_name in initial:
        collection = collections.by_item_type.get(collection_name, [])
        # for snovault test application, there are no users or keys
        if types is not None and collection_name not in types:
            continue
        for uuid in collection:
            yield str(uuid)
    for collection_name in sorted(collections.by_item_type):
        if collection_name in initial:
            continue
        if types is not None and collection_name not in types:
            continue
        collection = collections.by_item_type[collection_name]
        for uuid in collection:
            yield str(uuid)


def get_xmin_from_es(es):
    try:
        status = es.get(index='meta', doc_type='meta', id='indexing')
    except NotFoundError:
        interval_settings = {"index": {"refresh_interval": "30s"}}
        es.indices.put_settings(index='meta', body=interval_settings)
        return None
    else:
        return status['_source']['xmin']


def get_uuid_store_from_es(es):
    try:
        status = es.get(index='meta', doc_type='meta', id='uuid_store')
    except NotFoundError:
        return None
    else:
        return status['_source']['uuids']
