import sys
if sys.version_info.major == 2:
    from future.standard_library import install_aliases
    install_aliases()
    import functools
    from backports.functools_lru_cache import lru_cache
    functools.lru_cache = lru_cache
import netaddr
from pyramid.config import Configurator
from pyramid.settings import (
    asbool,
)
from .calculated import calculated_property  # noqa
from .config import (  # noqa
    abstract_collection,
    collection,
    root,
)
from .interfaces import *  # noqa
from .resources import (  # noqa
    AbstractCollection,
    Collection,
    Item,
    Resource,
    Root,
    display_title_schema
)
from .schema_utils import load_schema  # noqa
from .upgrader import upgrade_step  # noqa
from .app import (
    app_version,
    session,
    configure_dbsession,
    changelogs,
    json_from_path,
    )
import logging
import os
from dcicutils.log_utils import set_logging



def includeme(config):
    config.include('pyramid_retry')
    config.include('pyramid_tm')
    config.include('.util')
    config.include('.stats')
    config.include('.batchupgrade')
    config.include('.calculated')
    config.include('.config')
    config.include('.connection')
    config.include('.embed')
    config.include('.json_renderer')
    config.include('.validation')
    config.include('.predicates')
    config.include('.invalidation')
    config.include('.upgrader')
    config.include('.aggregated_items')
    config.include('.storage')
    config.include('.typeinfo')
    config.include('.resources')
    config.include('.attachment')
    config.include('.schema_graph')
    config.include('.jsonld_context')
    config.include('.schema_views')
    config.include('.crud_views')
    config.include('.indexing_views')
    config.include('.resource_views')


def main(global_config, **local_config):
    """ This function returns a Pyramid WSGI application.
    """
    settings = global_config
    settings.update(local_config)

    set_logging(in_prod=settings.get('production'))
    # set_logging(settings.get('elasticsearch.server'), settings.get('production'))

    # TODO - these need to be set for dummy app
    # settings['snovault.jsonld.namespaces'] = json_asset('snovault:schemas/namespaces.json')
    # settings['snovault.jsonld.terms_namespace'] = 'https://www.encodeproject.org/terms/'
    settings['snovault.jsonld.terms_prefix'] = 'snovault'

    config = Configurator(settings=settings)
    from .elasticsearch import APP_FACTORY
    config.registry[APP_FACTORY] = main  # used by mp_indexer
    config.include(app_version)

    config.include('pyramid_multiauth')  # must be before calling set_authorization_policy
    from pyramid_localroles import LocalRolesAuthorizationPolicy
    # Override default authz policy set by pyramid_multiauth
    config.set_authorization_policy(LocalRolesAuthorizationPolicy())
    config.include(session)

    config.include(configure_dbsession)
    config.include('snovault')
    config.commit()  # commit so search can override listing

    config.include('.renderers')

    # only include this stuff if we're testing
    if asbool(settings.get('testing', False)):
        config.include('snovault.tests.testing_views')
        config.include('snovault.tests.authentication')
        config.include('snovault.tests.root')
        if settings.get('elasticsearch.server'):
            config.include('snovault.tests.search')

    if 'elasticsearch.server' in config.registry.settings:
        config.include('snovault.elasticsearch')

    config.include(changelogs)

    # TODO This is optional AWS only - possibly move to a plug-in
    aws_ip_ranges = json_from_path(settings.get('aws_ip_ranges_path'), {'prefixes': []})
    config.registry['aws_ipset'] = netaddr.IPSet(
        record['ip_prefix'] for record in aws_ip_ranges['prefixes'] if record['service'] == 'AMAZON')

    # Load upgrades last so that all views (including testing views) are
    # registered.
    #config.include('.upgrade')

    app = config.make_wsgi_app()

    return app