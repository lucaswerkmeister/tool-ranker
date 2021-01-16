import pytest  # type: ignore
from werkzeug.routing import Map

from converters import BadRankException, BadWikiException, \
    RankConverter, WikiConverter


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
