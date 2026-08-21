from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Отдаём с корня (а не из /static/), чтобы scope service worker'а покрывал весь сайт.
    path(
        'sw.js',
        TemplateView.as_view(template_name='sw.js', content_type='application/javascript'),
        name='service_worker',
    ),
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'icons/icon-192.png', permanent=True)),
    path('legal/offer/', TemplateView.as_view(template_name='legal/offer.html'), name='offer'),

    path('', include('apps.orders.urls')),
    path('', include('apps.reports.urls')),
    path('', include('apps.payments.urls')),
    path('', include('apps.notifications.urls')),
    path('', include('apps.integrations.urls')),
    path('collectors/', include('apps.collectors.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
