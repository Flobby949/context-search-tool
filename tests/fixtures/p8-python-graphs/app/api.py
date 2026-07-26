import json
import app.service as svc
from app.clients.text import TextClient
from .service import build_service


class ApiHandler:
    def handle(self, payload):
        return build_service().run(payload)

    async def handle_async(self, payload):
        return svc.run_async(payload)

    class Pagination:
        def page_size(self):
            return 20


def make_handler():
    return ApiHandler()


async def stream_handler():
    return TextClient()
