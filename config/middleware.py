import json
import logging
import time

logger = logging.getLogger('planner')


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration_ms = round((time.time() - start) * 1000)

        user = getattr(request, 'user', None)
        logger.info(json.dumps({
            'method': request.method,
            'path': request.path,
            'status': response.status_code,
            'duration_ms': duration_ms,
            'user': user.email if user and user.is_authenticated else 'anonymous',
        }))
        return response
