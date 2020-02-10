"""
Cached views used when model was pulled from elasticsearch.
In some cases, use these views to render object and embedded content.
Leverages interfaces.ICachedItem as a provided interface for resources
from Elasticsearch. See esstorage.CachedModel and the following docs:
https://zopeinterface.readthedocs.io/en/stable/api.html#zope.interface.declarations.alsoProvides
"""

import sys

from pyramid.httpexceptions import HTTPForbidden
from pyramid.view import view_config

from .interfaces import ICachedItem
from ..resource_views import (
    item_view_embedded,
    item_view_object,
    item_view_page,
    item_view_expand
)
from ..indexing_views import item_index_data
from ..util import debug_log


def includeme(config):
    config.scan(__name__)


@view_config(context=ICachedItem, request_method='GET', name='embedded')
@debug_log
def cached_view_embedded(context, request):
    source = context.model.source
    allowed = set(source['principals_allowed']['view'])
    if allowed.isdisjoint(request.effective_principals):
        raise HTTPForbidden()
    return filter_embedded(source['embedded'], request.effective_principals)


_skip_fields = ['@type', 'principals_allowed']
def filter_embedded(embedded, effective_principals):
    """
    Filter the embedded items by principals_allowed, replacing them with
    a 'no view allowed' error message if the effective principals on the
    request are disjointed
    """
    _skip_fields = ['@type', 'principals_allowed']
    # handle dictionary
    if isinstance(embedded, dict):
        if 'principals_allowed' in embedded.keys():
            obj_princ = embedded.get('principals_allowed')
            allowed = set(obj_princ['view'])
            if allowed.isdisjoint(effective_principals):
                embedded = {'error': 'no view permissions'}
                return embedded

        for name, obj in embedded.items():
            if isinstance(obj, (dict, list)) and name not in _skip_fields:
                embedded[name] = filter_embedded(obj, effective_principals)

    # handle array
    elif isinstance(embedded, list):
        for idx, item in enumerate(embedded):
            embedded[idx] = filter_embedded(item, effective_principals)

    # default just return the sucker
    return embedded


@view_config(context=ICachedItem, permission='view', request_method='GET',
             name='embedded')
def cached_view_embedded(context, request):
    """
    Use the 'embedded' view that is stored the ElasticSearch unless we
    are using an Item with 'elasticsearch' properties_datastore, in which case
    we may have to generate the view dynamically if indexing or it doesn't yet
    exist
    """
    source = context.model.source
    # generate view if this item uses ES as primary datastore or indexing
    if (context.properties_datastore == 'elasticsearch' and
        ('embedded' not in source or request._indexing_view is True)):
        embedded = item_view_embedded(context, request)
    else:
        embedded = source['embedded']

    # permission checking on embedded objects
    allowed = set(embedded['principals_allowed']['view'])
    if allowed.isdisjoint(request.effective_principals):
        raise HTTPForbidden()
    return filter_embedded(embedded, request.effective_principals)


@view_config(context=ICachedItem, permission='view', request_method='GET',
             name='object')
@debug_log
def cached_view_object(context, request):
    """
    Use the 'object' view that is stored the ElasticSearch unless we
    are using an Item with 'elasticsearch' used_datastore, in which case we
    may have to generate the view dynamically if indexing or it doesn't yet
    exist
    """
    source = context.model.source
    # generate view if this item uses ES as primary datastore or indexing
    if (context.properties_datastore == 'elasticsearch' and
        ('object' not in source or request._indexing_view is True)):
        object = item_view_object(context, request)
    else:
        object = source['object']

    # permission checking. Is this redundant with permission set on view?
    allowed = set(object['principals_allowed']['view'])
    if allowed.isdisjoint(request.effective_principals):
        raise HTTPForbidden()
    return object


@view_config(context=ICachedItem, permission='view_raw', request_method='GET',
             name='raw')
def cached_view_raw(context, request):
    """
    Must generate this view because it's not stored in ES source. Add 'uuid'
    to the item properties to be consistent with the regular 'raw' view
    """
    source = context.model.source
    props = source['properties']
    # add uuid to raw view
    props['uuid'] = source['uuid']
    return props


@view_config(context=ICachedItem, permission='view', request_method='GET',
             name='page')
def cached_view_page(context, request):
    """
    Must generate this view because it's not stored in ES source
    """
    return item_view_page(context, request)


@view_config(context=ICachedItem, permission='expand', request_method='GET',
             name='expand')
def cached_view_expand(context, request):
    """
    Must generate this view because it's not stored in ES source
    """
    return item_view_expand(context, request)


@view_config(context=ICachedItem, permission='index', request_method='GET',
             name='index-data')
def cached_index_data(context, request):
    """
    Must generate this view because it's not stored in ES source
    """
    return item_index_data(context, request)
