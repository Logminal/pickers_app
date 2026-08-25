// Подключение push-уведомлений браузера на странице /notifications/settings/.
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

function getCsrfToken() {
    return document.querySelector('input[name=csrfmiddlewaretoken]').value;
}

document.addEventListener('DOMContentLoaded', function () {
    const btn = document.getElementById('push-toggle-btn');
    const statusEl = document.getElementById('push-status');
    const vapidKey = btn ? btn.dataset.vapidKey : null;
    if (!btn) return;

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        btn.disabled = true;
        statusEl.textContent = 'Этот браузер не поддерживает push-уведомления.';
        return;
    }
    if (!vapidKey) {
        btn.disabled = true;
        statusEl.textContent = 'Push пока не настроен администратором.';
        return;
    }

    btn.addEventListener('click', async function () {
        btn.disabled = true;
        try {
            const registration = await navigator.serviceWorker.ready;
            const existing = await registration.pushManager.getSubscription();

            if (btn.dataset.action === 'disable') {
                if (existing) {
                    await fetch('/notifications/push/unsubscribe/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({ endpoint: existing.endpoint }),
                    });
                    await existing.unsubscribe();
                }
                window.location.reload();
                return;
            }

            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                statusEl.textContent = 'Разрешение на уведомления не выдано.';
                btn.disabled = false;
                return;
            }

            const subscription = existing || await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(vapidKey),
            });

            await fetch('/notifications/push/subscribe/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify(subscription.toJSON()),
            });
            window.location.reload();
        } catch (err) {
            statusEl.textContent = 'Не удалось подключить уведомления: ' + err.message;
            btn.disabled = false;
        }
    });
});
