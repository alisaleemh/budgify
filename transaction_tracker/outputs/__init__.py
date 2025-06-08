# transaction_tracker/outputs/__init__.py
from importlib import import_module

def get_output(name, config):
    path = config['output_modules'][name]
    module_name, cls_name = path.rsplit('.', 1)
    mod = import_module(module_name)
    return getattr(mod, cls_name)(config)