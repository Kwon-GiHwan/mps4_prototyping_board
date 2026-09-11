"""Completion-visibility successor, pending qualification on the build environment."""

from . import (
    constants, errors, c_lexical, c_addresses, elf_analysis, source_loops,
    source_storage, source_cleanup, source_confinement, source_contracts,
    image_contracts, cli,
)
from .errors import GateError
from .source_contracts import verify_generated_sources
from .image_contracts import (
    verify_linked_image, verify_read_order_equivalence, verify_common_tail_is_shared,
)
from .cli import main

IMPLEMENTATION_MODULES = (
    constants, errors, c_lexical, c_addresses, elf_analysis, source_loops,
    source_storage, source_cleanup, source_confinement, source_contracts,
    image_contracts, cli,
)
