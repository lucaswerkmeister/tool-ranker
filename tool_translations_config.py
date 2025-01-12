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
        'edit-must-log-in': [
            'url',
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
        'edit-no-statements': [
            'entity',
            'property',
        ],
        'batch-query-collective-input-wdqs': [
            'url',
        ],
        'batch-query-individual-input-wdqs': [
            'url',
        ],
        'batch-list-collective-links': [
            'url_individual',
        ],
        'batch-list-collective-links-with-qs': [
            'url_individual',
            'url_query',
        ],
        'batch-list-individual-links': [
            'url_collective',
        ],
        'batch-list-individual-links-with-qs': [
            'url_collective',
            'url_query',
        ],
        'batch-query-collective-links': [
            'url_individual',
            'url_list',
        ],
        'batch-query-individual-links': [
            'url_collective',
            'url_list',
        ],
        'error-no-such-entity': [
            'entity_id',
            'wiki',
        ],
    },
    allowed_html_elements={
        'code': set(),
    },
    check_translations=False,
)
