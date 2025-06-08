# transaction_tracker/loaders/__init__.py
from importlib import import_module

def get_loader(name, config):
    loader_path = config['bank_loaders'][name]
    module_name, cls_name = loader_path.rsplit('.', 1)
    mod = import_module(module_name)
    return getattr(mod, cls_name)()