'use strict';

window.addEventListener('DOMContentLoaded', () => {
    const form = document.forms[0],
          wikiSelect = form.wiki,
          entityIdInput = form.entity_id;

    function updateEntityIdPlaceholder() {
        // adjust placeholder per templates/index.html
        switch (wikiSelect.value) {
        case 'www.wikidata.org':
        case 'test.wikidata.org':
            entityIdInput.placeholder = entityIdInput.dataset.placeholderWikidata;
            break;
        case 'commons.wikimedia.org':
        case 'test-commons.wikimedia.org':
            entityIdInput.placeholder = entityIdInput.dataset.placeholderCommons;
            break;
        }
    }

    wikiSelect.addEventListener('change', updateEntityIdPlaceholder);
    updateEntityIdPlaceholder(); // in case the browser remembered the wiki on soft reload
});
