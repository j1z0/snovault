import pytest
from snovault import TYPES
TYPE_NAMES = ['TestingPostPutPatchSno', 'TestingDownload']

""" Get all item types from schema names """
def get_parameterized_names():
    import os
    return [name.split('.')[0] for name in os.listdir(os.getcwd() + '/src/snovault/test_schemas')]

PARAMETERIZED_NAMES = get_parameterized_names()


@pytest.mark.parametrize('item_type', PARAMETERIZED_NAMES)
def test_collections(testapp, item_type):
    """ Get all item types, check they are in the response """
    res = testapp.get('/' + item_type).follow(status=200)
    assert item_type.encode('utf-8') in res.body


# XXX: Perhaps needs an additinal fixture to insert some test data?
@pytest.mark.slow
@pytest.mark.parametrize('item_type', PARAMETERIZED_NAMES)
def test_html_pages(testapp, item_type):
    res = testapp.get('/%s?limit=all' % item_type).follow(status=200)
    for item in res.json['@graph']:
        res = testapp.get(item['@id'])
        assert res.body.startswith(b'<!DOCTYPE html>')
        assert item_type.encode('utf-8') in res.body


# XXX: Perhaps needs an additinal fixture to insert some test data?
@pytest.mark.slow
@pytest.mark.parametrize('item_type', PARAMETERIZED_NAMES)
def test_html_server_pages(item_type, wsgi_server):
    from webtest import TestApp
    testapp = TestApp(wsgi_server)
    res = testapp.get(
        '/%s?limit=all' % item_type,
        headers={'Accept': 'application/json'},
    ).follow(
        status=200,
        headers={'Accept': 'application/json'},
    )
    for item in res.json['@graph']:
        res = testapp.get(item['@id'], status=200)
        assert res.body.startswith(b'<!DOCTYPE html>')
        assert item_type.encode('utf-8') in res.body
        assert b'Internal Server Error' not in res.body


@pytest.mark.parametrize('item_type', PARAMETERIZED_NAMES)
def test_json(testapp, item_type):
    """ Check that when we get proper item types """
    res = testapp.get('/' + item_type).follow(status=200)
    assert (item_type + 'Collection') in res.json['@type']


def test_json_basic_auth(anontestapp):
    from base64 import b64encode
    from pyramid.compat import ascii_native_
    url = '/'
    value = "Authorization: Basic %s" % ascii_native_(b64encode(b'nobody:pass'))
    res = anontestapp.get(url, headers={'Authorization': value}, status=401)
    assert res.content_type == 'application/json'


def test_home_json(testapp):
    res = testapp.get('/', status=200)
    assert res.json['@type']


def test_vary_json(anontestapp):
    res = anontestapp.get('/', status=200)
    assert res.vary is not None
    assert 'Accept' in res.vary


def test_collection_post_bad_json(testapp):
    item = {'foo': 'bar'}
    res = testapp.post_json('/embedding-tests', item, status=422)
    assert res.json['status'] == 'error'


def test_collection_post_malformed_json(testapp):
    item = '{'
    headers = {'Content-Type': 'application/json'}
    res = testapp.post('/embedding-tests', item, status=400, headers=headers)
    assert res.json['detail'].startswith('Expecting')


def test_collection_post_missing_content_type(testapp):
    item = '{}'
    testapp.post('/embedding-tests', item, status=415)


def test_collection_post_bad(anontestapp):
    from base64 import b64encode
    from pyramid.compat import ascii_native_
    value = "Authorization: Basic %s" % ascii_native_(b64encode(b'nobody:pass'))
    anontestapp.post_json('/embedding-tests', {}, headers={'Authorization': value}, status=401)


@pytest.mark.slow
def test_collection_limit(testapp):
    """ Post 3 EmbeddingTests, check that limit=all, limit=2 works """
    obj1 = {
        'title': "Testing1",
        'description': "This is testig object 1",
    }
    obj2 = {
        'title': "Testing2",
        'description': "This is testig object 2",
    }
    obj3 = {
        'title': "Testing3",
        'description': "This is testig object 3",
    }
    testapp.post_json('/embedding-tests', obj1, status=201)
    testapp.post_json('/embedding-tests', obj2, status=201)
    testapp.post_json('/embedding-tests', obj3, status=201)
    res_all = testapp.get('/embedding-tests/?limit=all', status=200)
    res_2 = testapp.get('/embedding-tests/?limit=2', status=200)
    assert len(res_all.json['@graph']) == 3
    assert len(res_2.json['@graph']) == 2


# XXX: embedding-tests has no 'actions', not clear where those are defined
def test_collection_actions_filtered_by_permission(testapp, anontestapp):
    res = testapp.get('/embedding-tests/')
    assert any(action for action in res.json.get('actions', []) if action['name'] == 'add')

    res = anontestapp.get('/embedding-tests/')
    assert not any(action for action in res.json.get('actions', []) if action['name'] == 'add')


def test_collection_put(testapp, execute_counter):
    """ Insert and udpate an item into a collection, verify it worked """
    initial = {
        'title': "Testing",
        'type': "object", # include a non-required field
        'description': "This is the initial insert",
    }
    item_url = testapp.post_json('/embedding-tests', initial).location

    with execute_counter.expect(1):
        item = testapp.get(item_url).json

    for key in initial:
        assert item[key] == initial[key]

    update = {
        'title': "New Testing",
        'type': "object",
        'description': "This is the updated insert",
    }
    testapp.put_json(item_url, update, status=200)

    res = testapp.get('/' + item['uuid']).follow().json

    for key in update:
        assert res[key] == update[key]


# XXX: new test
def test_invalid_collection_put(testapp):
    """ Tests that inserting various invalid items will appropriately fail """
    missing_required = {
        'title': "Testing",
        'type': "object"
    }
    testapp.post_json('/embedding-tests', missing_required, status=422)

    nonexistent_field = {
        'title': "Testing",
        'type': "string",
        'descriptionn': "This is a descriptionn", # typo
    }
    testapp.post_json('/embedding-tests', nonexistent_field, status=422)

    valid = {
        'title': "Testing",
        'type': "object", 
        'description': "This is a valid object",
    }
    invalid_update = {
        'descriptionn': "This is an invalid update",
    }
    item_url = testapp.post_json('/embedding-tests', valid, status=201).location
    testapp.put_json(item_url, invalid_update, status=422)


# XXX: first part of this test works but second will not since it refers to pages
def test_page_toplevel(anontestapp):
    res = anontestapp.get('/embedding-tests/', status=200)
    assert res.json['@id'] == '/embedding-tests/'


# cant run, terms does not have submitted_by
def test_jsonld_term(testapp):
    res = testapp.get('/embedding-tests/attachment')
    import pdb; pdb.set_trace()
    assert res.json

# works as is
def test_jsonld_context(testapp):
    res = testapp.get('/terms/', status=200)
    assert res.json

# works without workbook?
# also not sure if it previously had any effect
# as status code was not checked, now looks for 200
@pytest.mark.slow
@pytest.mark.parametrize('item_type', PARAMETERIZED_NAMES)
def test_index_data_workbook(testapp, indexer_testapp, item_type):
    res = testapp.get('/%s?limit=all' % item_type).follow(status=200)
    for item in res.json['@graph']:
        indexer_testapp.get(item['@id'] + '@@index-data', status=200)

# works as it (if x failed is expected, which i think it is)
@pytest.mark.xfail
def test_abstract_collection(testapp, experiment):
    testapp.get('/Dataset/{accession}'.format(**experiment))
    testapp.get('/datasets/{accession}'.format(**experiment))


# XXX: Instead of checking html we just check to see if it can be reached
def test_home(testapp):
    testapp.get('/', status=200)


# works as is
@pytest.mark.parametrize('item_type', TYPE_NAMES)
def test_profiles(testapp, item_type):
    from jsonschema_serialize_fork import Draft4Validator
    res = testapp.get('/profiles/%s.json' % item_type).maybe_follow(status=200)
    errors = Draft4Validator.check_schema(res.json)
    assert not errors
    # added from snovault.schema_views._annotated_schema
    assert 'rdfs:seeAlso' in res.json
    assert 'rdfs:subClassOf' in res.json
    assert 'children' in res.json
    assert res.json['isAbstract'] is False


# needs modification?
# passes 'AbstractItemTest'
# there are no other abstract collections here to use?
@pytest.mark.parametrize('item_type', ['AbstractItemTest'])
def test_profiles_abstract(testapp, item_type):
    from jsonschema_serialize_fork import Draft4Validator
    res = testapp.get('/profiles/%s.json' % item_type).maybe_follow(status=200)
    errors = Draft4Validator.check_schema(res.json)
    assert not errors
    # added from snovault.schema_views._annotated_schema
    assert 'rdfs:seeAlso' in res.json
    # Item/item does not have subClass
    if item_type.lower() == 'item':
        assert 'rdfs:subClassOf' not in res.json
    else:
        assert 'rdfs:subClassOf' in res.json
    # abstract types wil have children
    assert len(res.json['children']) >= 1
    assert res.json['isAbstract'] is True


# works as is
def test_profiles_all(testapp, registry):
    from jsonschema_serialize_fork import Draft4Validator
    res = testapp.get('/profiles/').maybe_follow(status=200)
    # make sure all types are present, including abstract types
    for ti in registry[TYPES].by_item_type.values():
        assert ti.name in res.json
    for ti in registry[TYPES].by_abstract_type.values():
        assert ti.name in res.json

# needs modification 
# gives 404, i think because /award
# doesn't exist in snovault
def test_bad_frame(testapp, award):
    res = testapp.get(award['@id'] + '?frame=bad', status=404)
    assert res.json['detail'] == '?frame=bad'
