window.addEventListener('DOMContentLoaded', () => {
    const selectAllButton = document.createElement('button'),
          selectNoneButton = document.createElement('button'),
          invertSelectionButton = document.createElement('button'),
          buttonsContainer = document.getElementById('selection_buttons');

    selectAllButton.innerText = buttonsContainer.dataset.selectAll;
    selectNoneButton.innerText = buttonsContainer.dataset.selectNone;
    invertSelectionButton.innerText = buttonsContainer.dataset.invertSelection;

    selectAllButton.addEventListener('click', () => {
        document.querySelectorAll('input[type=checkbox]').forEach( checkbox => {
            checkbox.checked = true;
        });
    });
    selectNoneButton.addEventListener('click', () => {
        document.querySelectorAll('input[type=checkbox]').forEach( checkbox => {
            checkbox.checked = false;
        });
    });
    invertSelectionButton.addEventListener('click', () => {
        document.querySelectorAll('input[type=checkbox]').forEach( checkbox => {
            checkbox.checked = !checkbox.checked;
        });
    });

    for (const button of [selectAllButton, selectNoneButton, invertSelectionButton]) {
        button.classList.add('btn', 'btn-secondary');
        button.type = 'button';
        buttonsContainer.append(button, ' ');
    }
});
