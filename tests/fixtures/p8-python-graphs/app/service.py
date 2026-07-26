import os, app.dupe
from . import clients
from .clients import text
from ..app import api  # escapes past the top-level package root


if os.name == "posix":
    class PosixService:
        def run(self, payload):
            import app.api
            return payload


class Service:
    if True:
        def conditional_method(self):
            return 1

    def run(self, payload):
        def local_helper():
            class LocalClass:
                pass

            return LocalClass

        return local_helper()


def build_service():
    from app.clients.text import TextClient

    class FactoryLocal:
        pass

    return Service()


async def run_async(payload):
    return payload
