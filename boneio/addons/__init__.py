"""Declarative BlackBone add-ons.

Only data-only ``modbus_device_pack`` packages are supported.  This package
must never import or invoke the experimental container extension runtime.
"""

from boneio.addons.errors import AddonError

__all__ = ["AddonError"]
