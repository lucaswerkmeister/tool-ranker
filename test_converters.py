import pytest  # type: ignore
from werkzeug.routing import Map

from converters import BadWikiException, WikiConverter


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
