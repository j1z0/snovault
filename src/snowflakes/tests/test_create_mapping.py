import pytest
from ..loadxl import ORDER
from snovault.elasticsearch.interfaces import ELASTIC_SEARCH

unit_test_type = 'snowflake'

@pytest.mark.parametrize('item_type', ORDER)
def test_type_mapping(registry, item_type):
    """
    Test basic mapping properties for each item type
    """
    from snovault.elasticsearch.create_mapping import type_mapping
    from snovault import TYPES
    mapping = type_mapping(registry[TYPES], item_type)
    assert mapping
    assert 'properties' in mapping
    assert 'include_in_all' in mapping

### unit tests for refactored create_mapping

def test_merge_schemas(registry):
    from snovault.elasticsearch.create_mapping import merge_schemas
    from snovault import TYPES
    test_schema = registry[TYPES][unit_test_type].schema
    test_subschema = test_schema['properties']['lab']
    res = merge_schemas(test_subschema, registry[TYPES])
    assert res
    assert res != test_subschema
    assert 'title' in res and res['title'] == 'Lab'

def test_update_mapping_by_embed(registry):
    from snovault.elasticsearch.create_mapping import update_mapping_by_embed
    from snovault import TYPES
    # first, test with dummy data
    curr_s = {'title': 'Test', 'type': 'string'}
    curr_e = 'test'
    curr_m = {'properties': {}}
    new_m = update_mapping_by_embed(curr_m, curr_e, curr_s)
    assert 'test' in new_m['properties']
    field_mapping = new_m['properties']['test']
    assert field_mapping['type'] == 'text'
    assert 'raw' in field_mapping['fields']
    assert 'lower_case_sort' in field_mapping['fields']
    # then test with real data and wildcard (*)
    test_schema = registry[TYPES][unit_test_type].schema
    test_subschema = test_schema['properties']['lab']
    curr_s = merge_schemas(test_subschema, registry[TYPES])
    curr_e = '*'
    curr_m = {'properties': {}}
    new_m = update_mapping_by_embed(curr_m, curr_e, curr_s)
    for s_key in curr_s['properties']:
        assert s_key in new_m['properties']
