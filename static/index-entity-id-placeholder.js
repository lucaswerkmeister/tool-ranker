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
            entityIdInput.placeholder = 'Q42, P31, L99…';
            break;
        case 'commons.wikimedia.org':
        case 'test-commons.wikimedia.org':
            entityIdInput.placeholder = 'M79869096 or File:DSC 0484 2-01.jpg';
            break;
        }
    }

    wikiSelect.addEventListener('change', updateEntityIdPlaceholder);
    updateEntityIdPlaceholder(); // in case the browser remembered the wiki on soft reload
});
