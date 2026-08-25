from django.urls import path

from .views import NotificationSettingsView, PushSubscribeView, PushUnsubscribeView

urlpatterns = [
    path('notifications/settings/', NotificationSettingsView.as_view(), name='notification_settings'),
    path('notifications/push/subscribe/', PushSubscribeView.as_view(), name='push_subscribe'),
    path('notifications/push/unsubscribe/', PushUnsubscribeView.as_view(), name='push_unsubscribe'),
]
