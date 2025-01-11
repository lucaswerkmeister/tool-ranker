from toolforge_i18n import TranslationsConfig

config = TranslationsConfig(
    variables={
        'nav-logged-in': [
            'user_link',
            'user_name',
        ],
        'index-placeholder-entity-id-wikidata': [
            'item_id',
            'property_id',
            'lexeme_id',
        ],
        'index-placeholder-entity-id-commons': [
            'mediainfo_id',
            'file_title',
        ],
        'edit-paragraph-1-logged-in': [
            'num_statements',
            'formatted_entity_id',
            'formatted_property_id',
        ],
        'edit-paragraph-1-logged-out': [
            'num_statements',
            'formatted_entity_id',
            'formatted_property_id',
        ],
    },
    check_translations=False,
)
