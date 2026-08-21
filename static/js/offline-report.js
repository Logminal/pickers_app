/**
 * Офлайн-черновики фотоотчёта (п.8 ТЗ): если на объекте плохая связь, форма
 * не теряется — сохраняется локально в IndexedDB и уходит на сервер сама,
 * как только связь восстановится (событие 'online' или повторное открытие
 * страницы), либо по кнопке «Отправить сейчас».
 *
 * Работает независимо от service worker'а — тот кэширует только GET-запросы,
 * саму отправку (POST) всегда ведёт этот скрипт.
 */
(function () {
    const DB_NAME = 'furniture_offline';
    const STORE_NAME = 'pending_reports';

    function openDb() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, 1);
            req.onupgradeneeded = () => {
                req.result.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    async function saveDraft(orderId, url, entries) {
        const db = await openDb();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readwrite');
            tx.objectStore(STORE_NAME).add({ orderId, url, entries, createdAt: new Date().toISOString() });
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
    }

    async function getDraftsForOrder(orderId) {
        const db = await openDb();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readonly');
            const req = tx.objectStore(STORE_NAME).getAll();
            req.onsuccess = () => resolve(req.result.filter((d) => d.orderId === orderId));
            req.onerror = () => reject(req.error);
        });
    }

    async function deleteDraft(id) {
        const db = await openDb();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readwrite');
            tx.objectStore(STORE_NAME).delete(id);
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
    }

    function formToEntries(form) {
        const fd = new FormData(form);
        return Array.from(fd.entries()); // [[key, value_or_File], ...] — дубли ключей (чек-лист) сохраняются как есть
    }

    function entriesToFormData(entries) {
        const fd = new FormData();
        entries.forEach(([key, value]) => fd.append(key, value));
        return fd;
    }

    async function submitEntries(url, entries) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch(url, {
                method: 'POST', body: entriesToFormData(entries),
                credentials: 'same-origin', signal: controller.signal,
            });
            clearTimeout(timeout);
            return response;
        } catch (err) {
            clearTimeout(timeout);
            throw err;
        }
    }

    async function flushDraft(draft, statusEl) {
        try {
            const response = await submitEntries(draft.url, draft.entries);
            // ВАЖНО: успех — это именно редирект (Django редиректит на карточку заявки
            // только при реальном успехе). Обычный 200 означает, что форма
            // перерисована с ошибками валидации — response.ok здесь ВСЕГДА true
            // (200 — валидный HTTP-статус), поэтому его нельзя использовать как
            // признак успеха, иначе черновик с ошибкой будет удалён молча.
            if (response.redirected) {
                await deleteDraft(draft.id);
                if (statusEl) statusEl.textContent = 'Черновик отправлен ✅';
                return true;
            }
            if (statusEl) {
                statusEl.textContent = 'Черновик не принят сервером (возможно, не хватает обязательных фото) '
                    + '— откройте заявку и заполните форму заново.';
            }
            return false;
        } catch (err) {
            return false; // всё ещё нет связи — оставляем черновик на потом
        }
    }

    function initUploadForm() {
        const form = document.querySelector('[data-offline-report-form]');
        if (!form) return;

        const orderId = form.dataset.orderId;
        const banner = document.getElementById('offline-banner');

        function showBanner(text, isError) {
            if (!banner) return;
            banner.textContent = text;
            banner.className = 'alert ' + (isError ? 'alert-warning' : 'alert-info');
            banner.classList.remove('d-none');
        }

        async function checkExistingDrafts() {
            const drafts = await getDraftsForOrder(orderId);
            if (drafts.length === 0) return;
            showBanner(
                `Есть несохранённый черновик отчёта от ${new Date(drafts[0].createdAt).toLocaleString('ru-RU')} `
                + '— пробуем отправить...',
                true,
            );
            for (const draft of drafts) {
                const ok = await flushDraft(draft, banner);
                if (ok) {
                    showBanner('Черновик успешно отправлен на проверку.', false);
                }
            }
        }

        form.addEventListener('submit', async function (event) {
            event.preventDefault();
            const entries = formToEntries(form);
            const submitBtn = form.querySelector('button[type=submit]');
            if (submitBtn) submitBtn.disabled = true;

            try {
                const response = await submitEntries(form.action, entries);
                // Успех определяем строго по редиректу (см. комментарий в flushDraft) —
                // обычный 200 означает форму, перерисованную с ошибками валидации.
                if (response.redirected) {
                    window.location.href = response.url;
                    return;
                }
                // Ошибки валидации — показываем ответ сервера как обычную страницу,
                // чтобы сборщик увидел, каких полей не хватает.
                const html = await response.text();
                document.open();
                document.write(html);
                document.close();
            } catch (err) {
                // Сети нет — сохраняем локально и не теряем то, что уже заполнено.
                await saveDraft(orderId, form.action, entries);
                showBanner(
                    'Нет связи с интернетом. Отчёт сохранён на телефоне и отправится сам, '
                    + 'как только появится связь — можно закрыть страницу.',
                    true,
                );
                if (submitBtn) submitBtn.disabled = false;
            }
        });

        window.addEventListener('online', () => checkExistingDrafts());
        checkExistingDrafts();
    }

    document.addEventListener('DOMContentLoaded', initUploadForm);
})();
