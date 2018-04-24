""" Test full indexing setup

The fixtures in this module setup a full system with postgresql and
elasticsearch running as subprocesses.
Does not include data dependent tests
"""

import pytest
import time
from snovault.elasticsearch.interfaces import ELASTIC_SEARCH, INDEXER_QUEUE, INDEXER_QUEUE_MIRROR
from snovault import (
    COLLECTIONS,
    TYPES,
)
from snovault.elasticsearch.create_mapping import check_if_index_exists

pytestmark = [pytest.mark.indexing]


@pytest.fixture(scope='session')
def app_settings(wsgi_server_host_port, elasticsearch_server, postgresql_server):
    from .testappfixtures import _app_settings
    settings = _app_settings.copy()
    settings['create_tables'] = True
    settings['persona.audiences'] = 'http://%s:%s' % wsgi_server_host_port
    settings['elasticsearch.server'] = elasticsearch_server
    settings['sqlalchemy.url'] = postgresql_server
    settings['collection_datastore'] = 'elasticsearch'
    settings['item_datastore'] = 'elasticsearch'
    settings['indexer'] = True
    settings['indexer.processes'] = 2
    return settings


@pytest.yield_fixture(scope='session')
def app(app_settings):
    from snovault import main
    app = main({}, **app_settings)

    yield app

    from snovault import DBSESSION
    DBSession = app.registry[DBSESSION]
    # Dispose connections so postgres can tear down.
    DBSession.bind.pool.dispose()


@pytest.fixture(autouse=True)
def teardown(app):
    import transaction
    from sqlalchemy import MetaData
    from zope.sqlalchemy import mark_changed
    from snovault import DBSESSION
    from snovault.elasticsearch import create_mapping
    create_mapping.run(app, skip_indexing=True)
    session = app.registry[DBSESSION]
    connection = session.connection().connect()
    meta = MetaData(bind=session.connection(), reflect=True)
    for table in meta.sorted_tables:
        print('Clear table %s' % table)
        print('Count before -->', str(connection.scalar("SELECT COUNT(*) FROM %s" % table)))
        connection.execute(table.delete())
        print('Count after -->', str(connection.scalar("SELECT COUNT(*) FROM %s" % table)), '\n')
    session.flush()
    mark_changed(session())
    transaction.commit()


def test_indexer_queue(app):
    import json
    indexer_queue_mirror = app.registry[INDEXER_QUEUE_MIRROR]
    # this is only set up for webprod/webprod2
    assert indexer_queue_mirror is None

    indexer_queue = app.registry[INDEXER_QUEUE]
    # unittesting the QueueManager
    assert indexer_queue.queue_url is not None
    assert indexer_queue.dlq_url is not None
    assert indexer_queue.second_queue_url is not None
    assert indexer_queue.defer_queue_url is not None
    test_message = 'abc123'
    to_index, failed = indexer_queue.add_uuids(app.registry, [test_message], strict=True)
    assert to_index == [test_message]
    assert not failed
    received = indexer_queue.receive_messages()
    assert len(received) == 1
    msg_body = json.loads(received[0]['Body'])
    assert isinstance(msg_body, dict)
    assert msg_body['uuid'] == test_message
    assert msg_body['strict'] is True
    # try to receive again (should be empty)
    received_2 = indexer_queue.receive_messages()
    assert len(received_2) == 0
    # replace into queue
    indexer_queue.replace_messages(received)
    # replace sets vis timeout to 5 seconds... so wait a bit first
    import time
    time.sleep(5.1)
    received = indexer_queue.receive_messages()
    assert len(received) == 1
    # finally, delete
    indexer_queue.delete_messages(received)
    time.sleep(2)
    msg_count = indexer_queue.number_of_messages()
    assert msg_count['primary_waiting'] == 0
    assert msg_count['primary_inflight'] == 0


def test_indexing_simple(app, testapp, indexer_testapp):
    from snovault.elasticsearch import indexer_utils
    # First post a single item so that subsequent indexing is incremental
    testapp.post_json('/testing-post-put-patch/', {'required': ''})
    res = indexer_testapp.post_json('/index', {'record': True})
    assert res.json['indexing_count'] == 1
    assert res.json['indexing_status'] == 'finished'
    assert res.json['errors'] is None
    res = testapp.post_json('/testing-post-put-patch/', {'required': ''})
    uuid = res.json['@graph'][0]['uuid']
    res = indexer_testapp.post_json('/index', {'record': True})
    assert res.json['indexing_count'] == 1
    res = testapp.get('/search/?type=TestingPostPutPatch')
    uuids = [indv_res['uuid'] for indv_res in res.json['@graph']]
    count = 0
    while uuid not in uuids and count < 20:
        time.sleep(1)
        res = testapp.get('/search/?type=TestingPostPutPatch')
        uuids = [indv_res['uuid'] for indv_res in res.json['@graph']]
        count += 1
    assert res.json['total'] >= 2
    assert uuid in uuids
    # test the meta index
    es = app.registry[ELASTIC_SEARCH]
    indexing_doc = es.get(index='meta', doc_type='meta', id='latest_indexing')
    indexing_source = indexing_doc['_source']
    assert 'indexing_finished' in indexing_source
    assert 'indexing_content' in indexing_source
    assert indexing_source['indexing_status'] == 'finished'
    assert indexing_source['indexing_count'] > 0
    testing_ppp_meta = es.get(index='meta', doc_type='meta', id='testing_post_put_patch')
    testing_ppp_source = testing_ppp_meta['_source']
    assert 'mappings' in testing_ppp_source
    assert 'settings' in testing_ppp_source


def test_indexing_queue_records(app, testapp, indexer_testapp):
    """
    Do a full test using different forms of create mapping and both sync
    and queued indexing.
    """
    from snovault.elasticsearch import create_mapping, indexer_utils
    from elasticsearch.exceptions import NotFoundError
    from datetime import datetime
    es = app.registry[ELASTIC_SEARCH]
    indexer_queue = app.registry[INDEXER_QUEUE]
    test_type = 'testing_post_put_patch'
    # no documents added yet
    doc_count = es.count(index=test_type, doc_type=test_type).get('count')
    assert doc_count == 0
    # post a document but do not yet index
    res = testapp.post_json('/testing-post-put-patch/', {'required': ''})
    doc_count = es.count(index=test_type, doc_type=test_type).get('count')
    assert doc_count == 0
    # indexing record should not yet exist (expect error)
    with pytest.raises(NotFoundError):
        es.get(index='meta', doc_type='meta', id='latest_indexing')
    res = indexer_testapp.post_json('/index', {'record': True})
    assert res.json['indexing_count'] == 1
    assert res.json['indexing_content']['type'] == 'queue'
    doc_count = es.count(index=test_type, doc_type=test_type).get('count')
    assert doc_count == 1
    # make sure latest_indexing doc matches
    indexing_doc = es.get(index='meta', doc_type='meta', id='latest_indexing')
    indexing_doc_source = indexing_doc.get('_source', {})
    assert indexing_doc_source.get('indexing_count') == 1
    # test timing in indexing doc
    assert indexing_doc_source.get('indexing_elapsed')
    indexing_start = indexing_doc_source.get('indexing_started')
    indexing_end = indexing_doc_source.get('indexing_finished')
    assert indexing_start and indexing_end
    time_start =  datetime.strptime(indexing_start, '%Y-%m-%dT%H:%M:%S.%f')
    time_done = datetime.strptime(indexing_end, '%Y-%m-%dT%H:%M:%S.%f')
    assert time_start < time_done
    # get indexing record by start_time
    indexing_record = es.get(index='meta', doc_type='meta', id=indexing_start)
    assert indexing_record.get('_source', {}).get('indexing_status') == 'finished'
    assert indexing_record.get('_source') == indexing_doc_source


def test_sync_and_queue_indexing(app, testapp, indexer_testapp):
    from snovault.elasticsearch import create_mapping, indexer_utils
    from elasticsearch.exceptions import NotFoundError
    from datetime import datetime
    es = app.registry[ELASTIC_SEARCH]
    indexer_queue = app.registry[INDEXER_QUEUE]
    test_type = 'testing_post_put_patch'
    # queued on post - total of one item queued
    res = testapp.post_json('/testing-post-put-patch/', {'required': ''})
    # synchronously index
    create_mapping.run(app, collections=[test_type], sync_index=True)
    time.sleep(6)
    doc_count = es.count(index=test_type, doc_type=test_type).get('count')
    assert doc_count == 1
    indexing_doc = es.get(index='meta', doc_type='meta', id='latest_indexing')
    assert indexing_doc['_source']['indexing_content']['type'] == 'sync'
    assert indexing_doc['_source']['indexing_count'] == 1
    # post second item to database but do not index (don't load into es)
    # queued on post - total of two items queued
    res = testapp.post_json('/testing-post-put-patch/', {'required': ''})
    time.sleep(2)
    doc_count = es.count(index=test_type, doc_type=test_type).get('count')
    # doc_count has not yet updated
    assert doc_count == 1
    # clear the queue by indexing and then run create mapping to queue the all items
    res = indexer_testapp.post_json('/index', {'record': True})
    assert res.json['indexing_count'] == 2
    time.sleep(2)
    create_mapping.run(app, collections=[test_type])
    res = indexer_testapp.post_json('/index', {'record': True})
    assert res.json['indexing_count'] == 2
    doc_count = es.count(index=test_type, doc_type=test_type).get('count')
    assert doc_count == 2


def test_queue_indexing_endpoint(app, testapp, indexer_testapp):
    es = app.registry[ELASTIC_SEARCH]
    # post a couple things
    testapp.post_json('/testing-post-put-patch/', {'required': ''})
    testapp.post_json('/testing-post-put-patch/', {'required': ''})
    # index these initial bad boys to get them out of the queue
    res = indexer_testapp.post_json('/index', {'record': True})
    assert res.json['indexing_count'] == 2
    # now use the queue_indexing endpoint to reindex them
    post_body = {
        'collections': ['testing_post_put_patch'],
        'strict': True
    }
    res = indexer_testapp.post_json('/queue_indexing', post_body)
    assert res.json['notification'] == 'Success'
    assert res.json['number_queued'] == 2
    res = indexer_testapp.post_json('/index', {'record': True})
    assert res.json['indexing_count'] == 2
    doc_count = es.count(index='testing_post_put_patch', doc_type='testing_post_put_patch').get('count')
    assert doc_count == 2

    # here are some failure situations
    post_body = {
        'collections': 'testing_post_put_patch',
        'strict': False
    }
    res = indexer_testapp.post_json('/queue_indexing', post_body)
    assert res.json['notification'] == 'Failure'
    assert res.json['number_queued'] == 0

    post_body = {
        'uuids': ['abc123'],
        'collections': ['testing_post_put_patch'],
        'strict': False
    }
    res = indexer_testapp.post_json('/queue_indexing', post_body)
    assert res.json['notification'] == 'Failure'
    assert res.json['number_queued'] == 0


def test_es_indices(app, elasticsearch):
    """
    Test overall create_mapping functionality using app.
    Do this by checking es directly before and after running mapping.
    Delete an index directly, run again to see if it recovers.
    """
    from snovault.elasticsearch.create_mapping import type_mapping, create_mapping_by_type, build_index_record
    es = app.registry[ELASTIC_SEARCH]
    item_types = app.registry[TYPES].by_item_type
    # check that mappings and settings are in index
    for item_type in item_types:
        item_mapping = type_mapping(app.registry[TYPES], item_type)
        try:
            item_index = es.indices.get(index=item_type)
        except:
            assert False
        found_index_mapping = item_index.get(item_type, {}).get('mappings').get(item_type, {}).get('properties', {}).get('embedded')
        found_index_settings = item_index.get(item_type, {}).get('settings')
        assert found_index_mapping
        assert found_index_settings
        # get the item record from meta and compare that
        full_mapping = create_mapping_by_type(item_type, app.registry)
        item_record = build_index_record(full_mapping, item_type)
        try:
            item_meta = es.get(index='meta', doc_type='meta', id=item_type)
        except:
            assert False
        meta_record = item_meta.get('_source', None)
        assert meta_record
        assert item_record == meta_record


def test_index_settings(app, testapp, indexer_testapp):
    from snovault.elasticsearch.create_mapping import index_settings
    test_type = 'testing_post_put_patch'
    es_settings = index_settings(test_type)
    max_result_window = es_settings['index']['max_result_window']
    # preform some initial indexing to build meta
    res = testapp.post_json('/testing-post-put-patch/', {'required': ''})
    res = indexer_testapp.post_json('/index', {'record': True})
    # need to make sure an xmin was generated for the following to work
    assert 'indexing_finished' in res.json
    es = app.registry[ELASTIC_SEARCH]
    curr_settings = es.indices.get_settings(index=test_type)
    found_max_window = curr_settings.get(test_type, {}).get('settings', {}).get('index', {}).get('max_result_window', None)
    # test one important setting
    assert int(found_max_window) == max_result_window


# some unit tests associated with build_index in create_mapping
def test_check_if_index_exists(app):
    es = app.registry[ELASTIC_SEARCH]
    test_type = 'testing_post_put_patch'
    exists = check_if_index_exists(es, test_type, True)
    assert exists
    # delete index
    es.indices.delete(index=test_type)
    exists = check_if_index_exists(es, test_type, True)
    assert not exists


def test_check_if_index_exists_can_used_cached_index_list():
    es = None
    cached_idx = {'testing_post_put_patch': 22}
    test_type = 'testing_post_put_patch'
    exists = check_if_index_exists(es, test_type, True, cached_idx)
    assert exists
    # delete index
    cached_idx = {'not_here':1}
    exists = check_if_index_exists(es, test_type, True, cached_idx)
    assert not exists


def test_get_previous_index_record(app):
    from snovault.elasticsearch.create_mapping import get_previous_index_record
    es = app.registry[ELASTIC_SEARCH]
    test_type = 'testing_post_put_patch'
    record = get_previous_index_record(True, es, test_type)
    assert record
    assert 'mappings' in record
    assert 'settings' in record
    # remove index record
    es.delete(index='meta', doc_type='meta', id=test_type)
    record = get_previous_index_record(True, es, test_type)
    assert record is None


def test_check_and_reindex_existing(app, testapp):
    from snovault.elasticsearch.create_mapping import check_and_reindex_existing
    es = app.registry[ELASTIC_SEARCH]
    test_type = 'testing_post_put_patch'
    # post an item but don't reindex
    # this will cause the testing-ppp index to queue reindexing when we call
    # check_and_reindex_existing
    res = testapp.post_json('/testing-post-put-patch/', {'required': ''})
    time.sleep(2)
    doc_count = es.count(index=test_type, doc_type=test_type).get('count')
    # doc_count has not yet updated
    assert doc_count == 0
    test_uuids = set()
    check_and_reindex_existing(app, es, test_type, test_uuids)
    assert(len(test_uuids)) == 1


def test_es_delete_simple(app, testapp, indexer_testapp, session):
    from snovault.interfaces import STORAGE
    from snovault.storage import (
        Resource,
        Key,
        PropertySheet,
        CurrentPropertySheet,
        TransactionRecord,
    )
    from snovault.elasticsearch.create_mapping import (
       run as run_create_mapping,
       check_and_reindex_existing
    )
    from snovault.commands.es_index_data import run as run_index_data
    indexer_queue = app.registry[INDEXER_QUEUE]
    ## Adding new test resource to DB
    storage = app.registry[STORAGE]
    test_type = 'testing_post_put_patch'
    test_body = {'required': '', 'simple1' : 'foo', 'simple2' : 'bar' }
    res = testapp.post_json('/testing-post-put-patch/', test_body)
    test_uuid = res.json['@graph'][0]['uuid']
    check = storage.get_by_uuid(test_uuid)

    assert str(check.uuid) == test_uuid

    ## Make sure we update ES index
    test_uuids = set()
    check_and_reindex_existing(app, app.registry[ELASTIC_SEARCH], test_type, test_uuids)

    assert test_uuid in test_uuids # Assert that this newly added Item is not yet indexed.
    # Then index it:
    indexer_queue.add_uuids(app.registry, list(test_uuids), strict=True)
    res = indexer_testapp.post_json('/index', {'record': True})
    time.sleep(5) # INDEXER performs a network request to ES server to index things. Whether we like it or not, this means it's async and we must wait.

    ## Now ensure that we do have it in ES:
    test_uuids_2 = set()
    check_and_reindex_existing(app, app.registry[ELASTIC_SEARCH], test_type, test_uuids_2)
    assert bool(test_uuids_2) == False # Ensure we don't have any more indices to reindex after indexing our newly added UUID/Item

    check_post_from_es = storage.read.get_by_uuid(test_uuid)
    check_post_from_rdb = storage.write.get_by_uuid(test_uuid)

    assert check_post_from_es is not None
    assert check_post_from_rdb is not None

    assert check_post_from_es.properties['simple1'] == test_body['simple1']
    assert check_post_from_es.properties['simple2'] == test_body['simple2']

    # The actual delete
    storage.delete_by_uuid(test_uuid) # We can optionally pass in test_type as well for better performance.

    check_post_from_rdb_2 = storage.write.get_by_uuid(test_uuid)

    assert check_post_from_rdb_2 is None

    time.sleep(5) # Allow time for ES API to send network request to ES server to perform delete.
    check_post_from_es_2 = storage.read.get_by_uuid(test_uuid)
    assert check_post_from_es_2 is None


def test_create_mapping_check_first(app, testapp, indexer_testapp):
    # ensure create mapping has been run
    from snovault.elasticsearch import create_mapping
    create_mapping.run(app, check_first=False, skip_indexing=True)
    es = app.registry[ELASTIC_SEARCH]
    meta = es.search(index='meta', body={'query': {'match_all': {}}})


    # clear one to make sure it gets put back
    assert es.get(index='meta', doc_type='meta', id='testing_post_put_patch')
    es.delete(index='meta', doc_type='meta', id='testing_post_put_patch')

    create_mapping.run(app, check_first=True, skip_indexing=True)
    meta2 = es.search(index='meta', body={'query': {'match_all': {}}})
    assert(len(meta['hits']['hits']) == len(meta2['hits']['hits']))
