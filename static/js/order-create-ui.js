// Создание заявки: подпись кнопки загрузки файла спецификации меняется на имя файла.
document.addEventListener('DOMContentLoaded', function () {
    const fileInput = document.getElementById('id_spec_file');
    const fileLabel = document.getElementById('spec-file-label');
    if (!fileInput || !fileLabel) return;

    const defaultText = fileLabel.textContent;
    fileInput.addEventListener('change', function () {
        if (fileInput.files.length) {
            fileLabel.textContent = '✓ ' + fileInput.files[0].name + ' · заменить';
            fileLabel.classList.add('form-file-btn-done');
        } else {
            fileLabel.textContent = defaultText;
            fileLabel.classList.remove('form-file-btn-done');
        }
    });
});
