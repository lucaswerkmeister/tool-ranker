from toolforge_i18n import TranslationsConfig

config = TranslationsConfig(
    variables={
        'nav-logged-in': [
            'user_link',
            'user_name',
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
