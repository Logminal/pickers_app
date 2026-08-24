// Живое обновление UI формы фотоотчёта: превью выбранного файла в слоте,
// прогресс-бар, счётчики, итог по доп. работам. Не подменяет серверную
// валидацию — required-атрибуты на инпутах остаются главным источником
// правды, это только подсказки пользователю до отправки.
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('report-upload-form');
    if (!form) return;

    const slots = Array.from(form.querySelectorAll('.photo-slot'));
    const requiredSlots = slots.filter(function (s) { return s.dataset.slotRequired === '1'; });
    const actInput = form.querySelector('input[name="act_photo"]');
    const actCard = document.getElementById('act-card');
    const actBtn = document.getElementById('act-upload-btn');
    const checklistInputs = Array.from(form.querySelectorAll('.checklist-input'));

    function slotInput(slot) {
        return slot.querySelector('input[type="file"]');
    }

    function updateSlot(slot) {
        const input = slotInput(slot);
        const has = input && input.files && input.files.length > 0;
        const thumb = slot.querySelector('.photo-slot-thumb');
        const icon = slot.querySelector('.photo-slot-thumb-icon');
        const hint = slot.querySelector('.photo-slot-hint');
        const btn = slot.querySelector('.photo-slot-btn');

        slot.classList.toggle('photo-slot-done', has);
        icon.textContent = has ? '✓' : '＋';
        hint.textContent = has ? input.files[0].name : 'Нажмите, чтобы прикрепить фото';
        btn.textContent = has ? 'Заменить' : 'Загрузить';
    }

    function updateAct() {
        if (!actInput) return;
        const has = actInput.files && actInput.files.length > 0;
        actCard.classList.toggle('act-card-done', has);
        actBtn.textContent = has ? ('✓ ' + actInput.files[0].name + ' · заменить') : '📎 Загрузить фото акта';
    }

    function updateProgress() {
        const doneReq = requiredSlots.filter(function (s) { const i = slotInput(s); return i && i.files.length > 0; }).length;
        const actDone = actInput && actInput.files && actInput.files.length > 0;
        const checkedCount = checklistInputs.filter(function (c) { return c.checked; }).length;

        const reqRatio = requiredSlots.length ? doneReq / requiredSlots.length : 1;
        const checkRatio = checklistInputs.length ? checkedCount / checklistInputs.length : 1;
        const pct = Math.round(reqRatio * 50 + (actDone ? 20 : 0) + checkRatio * 30);
        const ready = doneReq === requiredSlots.length && actDone && checkedCount === checklistInputs.length;

        const fill = document.getElementById('upload-progress-fill');
        const label = document.getElementById('upload-progress-label');
        if (fill) {
            fill.style.width = pct + '%';
            fill.style.background = ready ? 'var(--success)' : pct > 50 ? '#c9922b' : 'var(--brand)';
        }
        if (label) {
            label.textContent = pct + '%';
            label.style.color = ready ? 'var(--success)' : pct > 50 ? '#c9922b' : 'var(--brand)';
        }

        const allSlots = slots.length;
        const doneAll = slots.filter(function (s) { const i = slotInput(s); return i && i.files.length > 0; }).length;
        const slotCountLabel = document.getElementById('slot-count-label');
        if (slotCountLabel) {
            slotCountLabel.textContent = doneAll + ' из ' + allSlots + ' · обяз. ' + doneReq + '/' + requiredSlots.length;
        }
        const checklistCountLabel = document.getElementById('checklist-count-label');
        if (checklistCountLabel) {
            checklistCountLabel.textContent = checkedCount + ' из ' + checklistInputs.length;
            checklistCountLabel.style.color = checkedCount === checklistInputs.length ? 'var(--success)' : 'var(--ink-faint)';
        }

        const missing = [];
        if (doneReq < requiredSlots.length) missing.push('обязательные фото (' + doneReq + '/' + requiredSlots.length + ')');
        if (!actDone) missing.push('акт приёма-передачи');
        if (checkedCount < checklistInputs.length) missing.push('чек-лист (' + checkedCount + '/' + checklistInputs.length + ')');

        const hint = document.getElementById('upload-blocked-hint');
        const submitBtn = document.getElementById('upload-submit-btn');
        if (hint) hint.textContent = missing.length ? 'Осталось: ' + missing.join(', ') : '';
        if (submitBtn) submitBtn.classList.toggle('btn-action-submit-ready', ready);
    }

    slots.forEach(function (slot) {
        const input = slotInput(slot);
        if (input) input.addEventListener('change', function () { updateSlot(slot); updateProgress(); });
    });
    if (actInput) actInput.addEventListener('change', function () { updateAct(); updateProgress(); });
    checklistInputs.forEach(function (c) { c.addEventListener('change', updateProgress); });

    function updateExtrasTotal() {
        const rows = form.querySelectorAll('.extras-row');
        let total = 0;
        rows.forEach(function (row) {
            const desc = row.querySelector('.extras-desc');
            const price = row.querySelector('.extras-price');
            if (desc.value.trim()) total += parseInt(price.value, 10) || 0;
        });
        const box = document.getElementById('extras-total');
        const valueEl = document.getElementById('extras-total-value');
        if (total > 0) {
            box.hidden = false;
            valueEl.textContent = total.toLocaleString('ru-RU') + ' ₽';
        } else {
            box.hidden = true;
        }
    }
    form.querySelectorAll('.extras-desc, .extras-price').forEach(function (el) {
        el.addEventListener('input', updateExtrasTotal);
    });

    slots.forEach(updateSlot);
    updateAct();
    updateProgress();
});
