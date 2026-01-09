"""Utility modules for DataArchive"""

from .power_manager import PowerManager, prevent_sleep
from .chkdsk_wrapper import ChkdskWrapper, ChkdskResult, run_chkdsk
from .registry_reader import (
    RegistryReader,
    RegistryValue,
    RegistryKey,
    RegistryReadResult,
    read_offline_registry,
    get_windows_version
)
from .hash_utils import (
    HashResult,
    compute_quick_hash,
    compute_sha256,
    hash_file,
    files_are_duplicates,
    generate_composite_key,
    parse_composite_key
)

__all__ = [
    'PowerManager',
    'prevent_sleep',
    'ChkdskWrapper',
    'ChkdskResult',
    'run_chkdsk',
    'RegistryReader',
    'RegistryValue',
    'RegistryKey',
    'RegistryReadResult',
    'read_offline_registry',
    'get_windows_version',
    # Hash utilities for duplicate detection
    'HashResult',
    'compute_quick_hash',
    'compute_sha256',
    'hash_file',
    'files_are_duplicates',
    'generate_composite_key',
    'parse_composite_key'
]
