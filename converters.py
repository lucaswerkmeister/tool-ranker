from typing import Set
from werkzeug.exceptions import BadRequest
from werkzeug.routing import BaseConverter, ValidationError


class PropertyIdConverter(BaseConverter):
    def to_python(self, value: str) -> str:
        if len(value) < 2:
            raise ValidationError('Property ID must have ≥2 characters')
        if value[0] != 'P':
            raise ValidationError('Property ID must start with P')
        if value[1] == '0':
            raise ValidationError('Property ID must not be zero-padded')
        numeric_part = value[1:]
        if not numeric_part.isascii() and numeric_part.isnumeric():
            raise ValidationError('Property ID must be (ASCII) numeric')
        return value

    def to_url(self, value: str) -> str:
        return value


class RankConverter(BaseConverter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_ranks = {
            'deprecated',
            'normal',
            'preferred',
        }

    def to_python(self, value: str) -> str:
        if value in self.allowed_ranks:
            return value
        raise BadRankException(self.allowed_ranks, value)

    def to_url(self, value: str) -> str:
        return value


class BadRankException(BadRequest):
    def __init__(self, allowed_ranks: Set[str], rank: str):
        super().__init__()
        self.description = f'Invalid rank {rank}, allowed ranks are: '
        first = True
        for allowed_rank in allowed_ranks:
            if first:
                first = False
            else:
                self.description += ', '
            self.description += allowed_rank


class WikiConverter(BaseConverter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_wikis = {
            'www.wikidata.org',
            'test.wikidata.org',
            'commons.wikimedia.org',
            'test-commons.wikimedia.org',
        }

    def to_python(self, value: str) -> str:
        if value in self.allowed_wikis:
            return value
        raise BadWikiException(self.allowed_wikis, value)

    def to_url(self, value: str) -> str:
        return value


class BadWikiException(BadRequest):
    def __init__(self, allowed_wikis: Set[str], wiki: str):
        super().__init__()
        self.description = f'Invalid wiki {wiki}, allowed wikis are: '
        first = True
        for allowed_wiki in allowed_wikis:
            if first:
                first = False
            else:
                self.description += ', '
            self.description += allowed_wiki
