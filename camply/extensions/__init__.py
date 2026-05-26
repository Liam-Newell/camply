"""
Camply Extensions

Optional, additive sub-packages that build on top of the core camply
search/notification pipeline without modifying it. Importing this
package registers any new CLI commands defined under it on the main
``camply`` Click command group.
"""

# Importing the sub-package registers its CLI command on
# ``camply.cli.camply_command_line`` as a side effect.
from camply.extensions import canada_filters  # noqa: F401
from camply.extensions import ontario_parks  # noqa: F401

__all__ = ["canada_filters", "ontario_parks"]
