import pytest  # type: ignore
from werkzeug.routing import Map, ValidationError

from converters import EntityIdConverter, PropertyIdConverter, \
    RankConverter, BadRankException, \
    WikiConverter, BadWikiException, \
    WikiWithQueryServiceConverter, WikiWithoutQueryServiceException


@pytest.mark.parametrize('entity_id', [
    'P1',
    'Q1',
    'M1',
    'L1',
    'L1-S1',
    'L1-F1',
    'Q2',
    'P31',
    'M56855503',
    'L123-S116',
])
def test_EntityIdConverter_valid(entity_id):
    converter = EntityIdConverter(Map())
    assert converter.to_python(entity_id) == entity_id
    assert converter.to_url(entity_id) == entity_id


@pytest.mark.parametrize('entity_id', [
    '31',
    'X123',
    'P031',
    'L031',
    'L031-S1',
    'L123-S01',
    'L123-F01',
    'L-S',
    'L-S1',
    'L1-S',
    'L1-X1',
    'L1-S٣١',
    'M٣١',
])
def test_EntityIdConverter_invalid(entity_id):
    converter = EntityIdConverter(Map())
    with pytest.raises(ValidationError):
        converter.to_python(entity_id)


@pytest.mark.parametrize('property_id', [
    'P1',
    'P2',
    'P31',
    'P5972',
    'P2147483647',
])
def test_PropertyIdConverter_valid(property_id):
    converter = PropertyIdConverter(Map())
    assert converter.to_python(property_id) == property_id
    assert converter.to_url(property_id) == property_id


@pytest.mark.parametrize('property_id', [
    'Q42',
    '31',
    'P031',
    'P٣١',
])
def test_PropertyIdConverter_invalid(property_id):
    converter = PropertyIdConverter(Map())
    with pytest.raises(ValidationError):
        converter.to_python(property_id)


@pytest.mark.parametrize('rank', [
    'deprecated',
    'normal',
    'preferred',
])
def test_RankConverter_valid(rank):
    converter = RankConverter(Map())
    assert converter.to_python(rank) == rank
    assert converter.to_url(rank) == rank


@pytest.mark.parametrize('rank', [
    'Deprecated',
    'NORMAL',
    'best',
    'truth',
])
def test_RankConverter_invalid(rank):
    converter = RankConverter(Map())
    with pytest.raises(BadRankException) as excinfo:
        converter.to_python(rank)
    assert rank in excinfo.value.get_description()
    assert 'normal' in excinfo.value.get_description()


@pytest.mark.parametrize('wiki', [
    'www.wikidata.org',
    'test.wikidata.org',
    'commons.wikimedia.org',
    'test-commons.wikimedia.org',
])
def test_WikiConverter_valid(wiki):
    converter = WikiConverter(Map())
    assert converter.to_python(wiki) == wiki
    assert converter.to_url(wiki) == wiki


@pytest.mark.parametrize('wiki', [
    'en.wikipedia.org',
    'en.wikipedia.beta.wmflabs.org',
    'en.wikipedia.org.google.com',
    'lucaswerkmeister.de',
])
def test_WikiConverter_invalid(wiki):
    converter = WikiConverter(Map())
    with pytest.raises(BadWikiException) as excinfo:
        converter.to_python(wiki)
    assert wiki in excinfo.value.get_description()
    assert 'www.wikidata.org' in excinfo.value.get_description()


@pytest.mark.parametrize('wiki', [
    'www.wikidata.org',
])
def test_WikiWithQueryServiceConverter_valid(wiki):
    converter = WikiWithQueryServiceConverter(Map())
    assert converter.to_python(wiki) == wiki
    assert converter.to_url(wiki) == wiki


@pytest.mark.parametrize('wiki', [
    'en.wikipedia.org',
    'en.wikipedia.beta.wmflabs.org',
    'en.wikipedia.org.google.com',
    'lucaswerkmeister.de',
])
def test_WikiWithQueryServiceConverter_bad(wiki):
    converter = WikiWithQueryServiceConverter(Map())
    with pytest.raises(BadWikiException) as excinfo:
        converter.to_python(wiki)
    assert wiki in excinfo.value.get_description()
    assert 'www.wikidata.org' in excinfo.value.get_description()


@pytest.mark.parametrize('wiki', [
    'test.wikidata.org',
    'test-commons.wikimedia.org',
])
def test_WikiWithQueryServiceConverter_without(wiki):
    converter = WikiWithQueryServiceConverter(Map())
    with pytest.raises(WikiWithoutQueryServiceException) as excinfo:
        converter.to_python(wiki)
    assert wiki in excinfo.value.get_description()
    assert 'www.wikidata.org' in excinfo.value.get_description()
