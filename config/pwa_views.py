import json
import os
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static


def service_worker(request):
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'sw.js')
    try:
        with open(sw_path) as f:
            content = f.read()
    except FileNotFoundError:
        content = ''
    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-store'
    return response


def offline(request):
    return render(request, 'offline.html')


def manifest(request):
    data = {
        "name": "Vacation Planner",
        "short_name": "Trips",
        "description": "Plan trips and track expenses",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#2563eb",
        "theme_color": "#2563eb",
        "icons": [
            {
                "src": static("icons/icon.svg"),
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": static("icons/icon.svg"),
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "maskable",
            },
        ],
    }
    response = HttpResponse(json.dumps(data), content_type='application/manifest+json')
    response['Cache-Control'] = 'public, max-age=3600'
    return response
