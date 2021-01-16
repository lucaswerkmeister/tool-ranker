from typing import Set
from werkzeug.exceptions import BadRequest
from werkzeug.routing import BaseConverter, ValidationError


class EntityIdConverter(BaseConverter):
    def to_python(self, value: str) -> str:
        if len(value) < 2:
            raise ValidationError('Entity ID must have ≥2 characters')
        if value[0] not in {'Q', 'P', 'L', 'M'}:
            raise ValidationError('Entity ID must start with Q, P, L, or M')
        if value[1] == '0':
            raise ValidationError('Entity ID must not be zero-padded')
        if value[0] == 'L':
            lexeme_id, _, subentity_id = value.partition('-')
            if len(lexeme_id) < 2:
                raise ValidationError('Lexeme ID must have ≥2 characters')
            lexeme_numeric_part = lexeme_id[1:]
            if not lexeme_numeric_part.isascii() \
               and lexeme_numeric_part.isnumeric():
                raise ValidationError('Lexeme ID must be (ASCII) numeric')
            if subentity_id:
                if len(subentity_id) < 2:
                    raise ValidationError('Lexeme sub-entity ID must '
                                          'have ≥2 characters')
                if subentity_id[0] not in {'S', 'F'}:
                    raise ValidationError('Lexeme sub-entity ID must '
                                          'start with S or F')
                if subentity_id[1] == '0':
                    raise ValidationError('Lexeme sub-entity ID must '
                                          'not be zero-padded')
                subentity_numeric_part = subentity_id[1:]
                if not subentity_numeric_part.isascii() \
                   and subentity_numeric_part.isnumeric():
                    raise ValidationError('Lexeme sub-entity ID must '
                                          'be (ASCII) numeric')
        else:
            numeric_part = value[1:]
            if not numeric_part.isascii() and numeric_part.isnumeric():
                raise ValidationError('Property ID must be (ASCII) numeric')
        return value

    def to_url(self, value: str) -> str:
        return value


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
