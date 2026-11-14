"""Import every appliance plugin so it registers itself with APPLIANCE_REGISTRY.

Adding a new appliance type (microwave, air fryer, coffee maker, ...) means
creating one new file in this folder and adding one import line here.
Nothing else in the integration needs to change.
"""

from . import (
    dishwasher,  # noqa: F401
    door,  # noqa: F401
    dryer,  # noqa: F401
    oven,  # noqa: F401
    refrigerator,  # noqa: F401
    washer,  # noqa: F401
)
