from copy import deepcopy
from .interfaces import CONNECTION
from past.builtins import basestring
from posixpath import join
from pyramid.compat import (
    native_,
    unquote_bytes_to_wsgi,
)
from pyramid.httpexceptions import HTTPNotFound
from pyramid.exceptions import URLDecodeError
from pyramid.traversal import find_resource
from pyramid.interfaces import IRoutesMapper
import logging
log = logging.getLogger(__name__)


def includeme(config):
    config.scan(__name__)
    config.add_renderer('null_renderer', NullRenderer)
    config.add_request_method(embed, 'embed')
    config.add_request_method(lambda request: set(), '_embedded_uuids', reify=True)
    config.add_request_method(lambda request: None, '__parent__', reify=True)


def make_subrequest(request, path):
    """ Make a subrequest

    Copies request environ data for authentication.

    May be better to just pull out the resource through traversal and manually
    perform security checks.
    """
    env = request.environ.copy()
    if path and '?' in path:
        path_info, query_string = path.split('?', 1)
        path_info = path_info
    else:
        path_info = path
        query_string = ''
    env['PATH_INFO'] = path_info
    env['QUERY_STRING'] = query_string
    subreq = request.__class__(env, method='GET', content_type=None,
                               body=b'')
    subreq.remove_conditional_headers()
    # XXX "This does not remove headers like If-Match"
    subreq.__parent__ = request
    return subreq


def embed(request, *elements, **kw):
    """ as_user=True for current user
    Pass in fields_to_embed as a keyword arg
    """
    # Should really be more careful about what gets included instead.
    # Cache cut response time from ~800ms to ~420ms.
    embed_cache = request.registry[CONNECTION].embed_cache
    print('--> %s' % len(embed_cache.cache))
    as_user = kw.get('as_user')
    path = join(*elements)
    path = unquote_bytes_to_wsgi(native_(path))
    # as_user controls whether or not the embed_cache is used
    if as_user is not None:
        result, embedded_uuids = _embed(request, path, as_user)
    else:
        # Carl: caching restarts at every call to embed()
        cached = embed_cache.get(path, None)
        if cached is None:
            cached = _embed(request, path)
            embed_cache[path] = cached
        result, embedded_uuids = cached
        result = deepcopy(result)
    log.debug('embed: %s', path)
    if not '@@audit' in path:
        request._embedded_uuids.update(embedded_uuids)
    return result


def _embed(request, path, as_user='EMBED'):
    # Carl: the subrequest is 'built' here, but not actually invoked
    subreq = make_subrequest(request, path)
    # do this because we want the embedded_uuids generated by @@embedded_uuids
    # for the @@audit view. Will default to @@object embedded_uuids if this
    # attr is not present (see item_view_audit in auditor.py)
    if '@@audit' in path and hasattr(request, '_embedded_uuids'):
            subreq._embedded_uuids = request._embedded_uuids
    subreq.override_renderer = 'null_renderer'
    subreq._is_indexing = request._is_indexing
    if as_user is not True:
        if 'HTTP_COOKIE' in subreq.environ:
            del subreq.environ['HTTP_COOKIE']
        subreq.remote_user = as_user
    try:
        result = request.invoke_subrequest(subreq)
    except HTTPNotFound:
        raise KeyError(path)
    return result, subreq._embedded_uuids


class NullRenderer:
    '''Sets result value directly as response.
    '''
    def __init__(self, info):
        pass

    def __call__(self, value, system):
        request = system.get('request')
        if request is None:
            return value
        request.response = value
        return None
