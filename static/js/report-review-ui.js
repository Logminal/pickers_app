// Проверка фотоотчёта: лайтбокс для фото и переключение панели "Отклонить"
// (текст причины) вместо стандартного Bootstrap collapse — вёрстка ближе к
// референсу, поведение то же.
document.addEventListener('DOMContentLoaded', function () {
    const lightbox = document.getElementById('review-lightbox');
    const lightboxImg = document.getElementById('review-lightbox-img');
    const lightboxLabel = document.getElementById('review-lightbox-label');
    const lightboxClose = document.getElementById('review-lightbox-close');

    document.querySelectorAll('[data-lightbox-src]').forEach(function (el) {
        el.addEventListener('click', function () {
            lightboxImg.src = el.dataset.lightboxSrc;
            lightboxLabel.textContent = el.dataset.lightboxLabel || '';
            lightbox.hidden = false;
        });
    });
    if (lightboxClose) lightboxClose.addEventListener('click', function () { lightbox.hidden = true; });
    if (lightbox) lightbox.addEventListener('click', function (e) { if (e.target === lightbox) lightbox.hidden = true; });

    const startReject = document.getElementById('review-start-reject');
    const cancelReject = document.getElementById('review-cancel-reject');
    const decisionButtons = document.getElementById('review-decision-buttons');
    const rejectPanel = document.getElementById('review-reject-panel');
    if (startReject && rejectPanel && decisionButtons) {
        startReject.addEventListener('click', function () {
            decisionButtons.hidden = true;
            rejectPanel.hidden = false;
            const textarea = document.getElementById('review-reject-reason');
            if (textarea) textarea.focus();
        });
    }
    if (cancelReject && rejectPanel && decisionButtons) {
        cancelReject.addEventListener('click', function () {
            rejectPanel.hidden = true;
            decisionButtons.hidden = false;
        });
    }
});
