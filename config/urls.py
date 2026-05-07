from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from config.pwa_views import service_worker, manifest, offline

urlpatterns = [
    path('sw.js', service_worker, name='service_worker'),
    path('manifest.json', manifest, name='manifest'),
    path('offline/', offline, name='offline'),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('planner.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
