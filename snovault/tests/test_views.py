import json
import os
import pytest

from base64 import b64encode
from jsonschema_serialize_fork import Draft4Validator
from pyramid.compat import ascii_native_
from ..interfaces import TYPES

# These are taken care of by pytest.ini and should not be explicitly repeated.
# -kmp 4-Jul-2020
#from .toolfixtures import registry, root


TYPE_NAMES = ['TestingPostPutPatchSno', 'TestingDownload']


def get_parameterized_names():
    """ Get all item types from schema names """
    return [name.split('.')[0] for name in os.listdir(os.getcwd() + '/snovault/test_schemas')]


PARAMETERIZED_NAMES = get_parameterized_names()

def test_nested_embed(testapp):

    td_res = testapp.post_json('/nested-object-link-target/',
                               {
                                   "associates": [{"x": "1", "y": "2", "z": "3"}],
                                   "title": "required title",
                                   "description": "foo",
                                   "uuid": "100a0bb8-2974-446b-a5de-6937aa313be4",
                               },
                               status=201).json
    res = testapp.post_json('/nested-embedding-container/',
                               {
                                   "link_to_nested_object": td_res['@graph'][0]['uuid'],
                                   "title": "required title",
                                   "description": "foo",
                                   "uuid": "b58bc82f-249e-418f-bbcd-8a80af2e58d3",
                               },
                               status=201).json
    embedded_json = testapp.get(res['@graph'][0]['@id'] + "?frame=embedded").json
    print(json.dumps(embedded_json, indent=2))

    link_to_nested_object = embedded_json['link_to_nested_object']
    assert 'associates' in link_to_nested_object
    [associate] = link_to_nested_object['associates']
    assert associate['x'] == '1'
    assert associate['y'] == '2'
    assert 'z' not in associate

def test_nested_embed_calculated(testapp):

    td_res = testapp.post_json('/nested-object-link-target/',
                               {
                                   "associates": [{"x": "1", "y": "2", "z": "3"}],
                                   "title": "required title",
                                   "description": "foo",
                                   "uuid": "100a0bb8-2974-446b-a5de-6937aa313be4",
                               },
                               status=201).json
    res = testapp.post_json('/nested-embedding-container/',
                               {
                                   "link_to_nested_object": td_res['@graph'][0]['uuid'],
                                   "title": "required title",
                                   "description": "foo",
                                   "uuid": "b58bc82f-249e-418f-bbcd-8a80af2e58d3",
                               },
                               status=201).json
    embedded_json = testapp.get(res['@graph'][0]['@id'] + "?frame=embedded").json
    print(json.dumps(embedded_json, indent=2))

    link_to_nested_object = embedded_json['link_to_nested_object']
    assert 'associates' in link_to_nested_object
    [associate] = link_to_nested_object['associates']
    assert associate['x'] == '1'
    assert associate['y'] == '2'
    assert 'z' not in associate

    nested_calculated_property = embedded_json['nested_calculated_property']
    for item in nested_calculated_property:
        assert 'associates' in item


def test_nested_embed_multi_trivial(testapp):

    td_res = testapp.post_json('/nested-object-link-target/',
                               {
                                   "associates": [{"x": "1", "y": "2", "z": "3"}],
                                   "title": "required title",
                                   "description": "foo",
                               },
                               status=201).json
    res = testapp.post_json('/nested-embedding-container/',
                               {
                                   "link_to_nested_objects": [td_res['@graph'][0]['uuid']],
                                   "title": "required title",
                                   "description": "foo",
                               },
                               status=201).json
    embedded_json = testapp.get(res['@graph'][0]['@id'] + "?frame=embedded").json
    print(json.dumps(embedded_json, indent=2))
    [item] = embedded_json['link_to_nested_objects']  # We only associated one uuid in our post
    [associate] = item['associates'] # We only described one associate in the target
    assert associate['x'] == '1'
    assert associate['y'] == '2'
    assert 'z' not in associate


def test_nested_embed_multi(testapp):

    n_targets = 5
    props = ["x", "y", "z"]
    embedded_props = ["x", "y"]
    unembedded_props = sorted(set(props) - set(embedded_props))
    assert unembedded_props == ["z"]  # a consistency check. needs to change if props or embedded props changes
    props_count = len(props)  # unless test changes, this is probably 3
    assert props_count == 3  # another consistency check. this needs to change if props changes.

    target_uuid_list = []
    for i in range(n_targets):
        # k will step by the number of properties (probably 3, for "x", "y", "z", but we'll keep it abstract)
        k = i * props_count
        # e.g., prop_bindings will take on {"x": "0", "y": "1", "z": "2"}, {"x": "3", "y": "4", "z": "5"}, ...
        prop_bindings = {key: str(k + pos) for pos, key in enumerate(props)}
        target_result = testapp.post_json('/nested-object-link-target/',
                                          {
                                              "associates": [prop_bindings],
                                              # Fields "title" and "description" are required, but might as well
                                              # include useful stuff in case it's needed for debugging. These values
                                              # do not affect the outcome. -kmp 4-Jul-2020
                                              "title": "Item {i} with props={props}".format(i=i, props=prop_bindings),
                                              "description": "This is item {}".format(i),
                                          },
                                          status=201).json
        uuid = target_result['@graph'][0]['uuid']
        target_uuid_list.append(uuid)
    res = testapp.post_json('/nested-embedding-container/',
                            {
                                "link_to_nested_objects": target_uuid_list,
                                "title": "Sample container for nested items",
                                "description": "This is just an example for testing.",
                            },
                            status=201).json
    embedded_json = testapp.get(res['@graph'][0]['@id'] + "?frame=embedded").json
    # This will show up if debugging is needed
    print(json.dumps(embedded_json, indent=2))
    items = embedded_json['link_to_nested_objects']
    assert len(items) == n_targets
    for i, item in enumerate(items):
        [associate] = item['associates']
        # Make sure that "x" and "y" (or whatever our embedded props are) exist in the example.
        assert all(isinstance(associate[prop], str) for prop in embedded_props)
        # Make sure that the fields we did NOT embed do not appear
        assert all(prop not in associate for prop in unembedded_props)
        # Get the values of each of the fields, which we expect to be strings coerceable to integers.
        nums = [int(associate[prop]) for prop in embedded_props]
        # for some item i, the numbers we'll expect are i*prop_count+pos
        k = i * props_count   # Truncate to block of 3. e.g., (0,1,2) or (9,10,11)
        for pos, prop in enumerate(embedded_props):
            assert nums[pos] == k + pos


@pytest.mark.parametrize('item_type', PARAMETERIZED_NAMES)
def test_collections(testapp, item_type):
    """ Get all item types, check they are in the response """
    res = testapp.get('/' + item_type).follow(status=200)
    assert item_type.encode('utf-8') in res.body


@pytest.mark.parametrize('item_type', PARAMETERIZED_NAMES)
def test_json(testapp, item_type):
    """ Check that when we get proper item types """
    res = testapp.get('/' + item_type).follow(status=200)
    assert (item_type + 'Collection') in res.json['@type']


def test_json_basic_auth(anontestapp):
    url = '/'
    value = "Authorization: Basic %s" % ascii_native_(b64encode(b'nobody:pass'))
    res = anontestapp.get(url, headers={'Authorization': value}, status=401)
    assert res.content_type == 'application/json'


def test_home_json(testapp):
    res = testapp.get('/', status=200)
    assert res.json['@type']


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
    value = "Authorization: Basic %s" % ascii_native_(b64encode(b'nobody:pass'))
    anontestapp.post_json('/embedding-tests', {}, headers={'Authorization': value}, status=401)


@pytest.mark.slow
def test_collection_limit(testapp):
    """ Post 3 EmbeddingTests, check that limit=all, limit=2 works """
    obj1 = {
        'title': "Testing1",
        'description': "This is testing object 1",
    }
    obj2 = {
        'title': "Testing2",
        'description': "This is testing object 2",
    }
    obj3 = {
        'title': "Testing3",
        'description': "This is testing object 3",
    }
    testapp.post_json('/embedding-tests', obj1, status=201)
    testapp.post_json('/embedding-tests', obj2, status=201)
    testapp.post_json('/embedding-tests', obj3, status=201)
    res_all = testapp.get('/embedding-tests/?limit=all', status=200)
    res_2 = testapp.get('/embedding-tests/?limit=2', status=200)
    assert len(res_all.json['@graph']) == 3
    assert len(res_2.json['@graph']) == 2

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


def test_page_toplevel(anontestapp):
    res = anontestapp.get('/embedding-tests/', status=200)
    assert res.json['@id'] == '/embedding-tests/'


def test_jsonld_context(testapp):
    res = testapp.get('/terms/', status=200)
    assert res.json


@pytest.mark.slow
@pytest.mark.parametrize('item_type', PARAMETERIZED_NAMES)
def test_index_data_workbook(testapp, indexer_testapp, item_type):
    res = testapp.get('/%s?limit=all' % item_type).follow(status=200)
    for item in res.json['@graph']:
        indexer_testapp.get(item['@id'] + '@@index-data', status=200)


@pytest.mark.xfail
def test_abstract_collection(testapp, experiment):
    testapp.get('/Dataset/{accession}'.format(**experiment))
    testapp.get('/datasets/{accession}'.format(**experiment))


def test_home(testapp):
    testapp.get('/', status=200)


@pytest.mark.parametrize('item_type', TYPE_NAMES)
def test_profiles(testapp, item_type):
    res = testapp.get('/profiles/%s.json' % item_type).maybe_follow(status=200)
    errors = Draft4Validator.check_schema(res.json)
    assert not errors
    # added from ..schema_views._annotated_schema
    assert 'rdfs:seeAlso' in res.json
    assert 'rdfs:subClassOf' in res.json
    assert 'children' in res.json
    assert res.json['isAbstract'] is False


@pytest.mark.parametrize('item_type', ['AbstractItemTest'])
def test_profiles_abstract(testapp, item_type):
    res = testapp.get('/profiles/%s.json' % item_type).maybe_follow(status=200)
    errors = Draft4Validator.check_schema(res.json)
    assert not errors
    # added from ..schema_views._annotated_schema
    assert 'rdfs:seeAlso' in res.json
    # Item/item does not have subClass
    if item_type.lower() == 'item':
        assert 'rdfs:subClassOf' not in res.json
    else:
        assert 'rdfs:subClassOf' in res.json
    # abstract types wil have children
    assert len(res.json['children']) >= 1
    assert res.json['isAbstract'] is True


def test_profiles_all(testapp, registry):
    res = testapp.get('/profiles/').maybe_follow(status=200)
    # make sure all types are present, including abstract types
    for ti in registry[TYPES].by_item_type.values():
        assert ti.name in res.json
    for ti in registry[TYPES].by_abstract_type.values():
        assert ti.name in res.json
