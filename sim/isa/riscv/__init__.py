# Re-export the new component-based RISCV config.
# The old Amaranth-based ISABase subclass is preserved in config_legacy.py
# for backward compatibility with the original app/flask_app.py.
from .config import RISCV
from .constants import REGISTER_NAMES
