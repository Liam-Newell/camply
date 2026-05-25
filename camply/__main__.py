"""
camply __main__.py CLI Wrapper
"""

from camply.cli import cli

# Importing the extensions package registers any additional CLI
# commands (e.g. ``camply canada-campsites``) on the main Click group.
import camply.extensions  # noqa: E402,F401

if __name__ == "__main__":
    cli()
