"""
Sandbox backend registry and factory.

The backend is selected at runtime via the ALETHEIA_SANDBOX environment
variable (.env): local (default — commands run directly) / bwrap (each
command wrapped in a bubblewrap namespace with the network blocked and
writes limited to the working directory and /tmp).

Backend modules are imported lazily inside create_sandbox so that only
the selected backend is loaded at startup.
"""
import importlib
import shutil

from core.sandbox.base import Sandbox

# backend name -> (module path, class name)
_SANDBOXES = {
    "local": ("core.sandbox.local", "LocalBackend"),
    "bwrap": ("core.sandbox.bwrap", "BwrapBackend"),
}


def create_sandbox(name: str) -> Sandbox:
    """Create a sandbox backend matching the backend name."""
    key = name.strip().lower()
    if key not in _SANDBOXES:
        raise ValueError(
            f"Unknown ALETHEIA_SANDBOX: {name!r} "
            f"(valid values: {', '.join(sorted(_SANDBOXES))})"
        )
    if key == "bwrap" and shutil.which("bwrap") is None:
        # Fail loudly rather than silently running unsandboxed.
        raise ValueError(
            "ALETHEIA_SANDBOX=bwrap requires the bwrap binary; "
            "install it with: sudo apt-get install bubblewrap"
        )
    module_path, class_name = _SANDBOXES[key]
    backend = getattr(importlib.import_module(module_path), class_name)
    return backend()
