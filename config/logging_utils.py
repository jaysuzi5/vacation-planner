import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            log_data['exc_info'] = self.formatException(record.exc_info)
        return json.dumps(log_data)
