"""Import every appliance plugin so it registers itself with APPLIANCE_REGISTRY.

Adding a new appliance type (microwave, air fryer, coffee maker, ...) means
creating one new file in this folder and adding one import line here.
Nothing else in the integration needs to change.
"""
from . import washer  # noqa: F401
from . import dryer  # noqa: F401
from . import dishwasher  # noqa: F401
from . import oven  # noqa: F401
from . import refrigerator  # noqa: F401
from . import door  # noqa: F401
