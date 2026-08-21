from django.urls import path

from .views import NotificationSettingsView

urlpatterns = [
    path('notifications/settings/', NotificationSettingsView.as_view(), name='notification_settings'),
]
