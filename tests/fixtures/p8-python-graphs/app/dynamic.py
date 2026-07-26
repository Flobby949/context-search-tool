import importlib


def load(name):
    module = importlib.import_module(name)
    other = __import__(name)
    return module, other
