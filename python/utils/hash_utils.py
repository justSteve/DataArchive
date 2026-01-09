"""
File Hashing Utilities for Duplicate Detection

Provides two hashing strategies:
1. Quick Hash: Fast preliminary check using first/last bytes + file size
2. SHA-256 Hash: Definitive content verification

Quick hash is used for initial duplicate detection, SHA-256 confirms matches.
"""

import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger

logger = get_logger(__name__)

# Quick hash parameters
QUICK_HASH_CHUNK_SIZE = 4096  # Bytes to read from start/end
MIN_SIZE_FOR_QUICK_HASH = 64  # Files smaller than this use full content


@dataclass
class HashResult:
    """Result of a file hashing operation"""
    file_path: str
    file_size: int
    quick_hash: Optional[str] = None
    sha256_hash: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'file_path': self.file_path,
            'file_size': self.file_size,
            'quick_hash': self.quick_hash,
            'sha256_hash': self.sha256_hash,
            'error': self.error
        }


def compute_quick_hash(file_path: str, chunk_size: int = QUICK_HASH_CHUNK_SIZE) -> Tuple[Optional[str], Optional[str]]:
    """
    Compute a quick hash for fast duplicate detection.

    The quick hash combines:
    - File size
    - First N bytes
    - Last N bytes (if file is large enough)

    This provides very fast duplicate candidate detection with low false positives.

    Args:
        file_path: Path to the file
        chunk_size: Bytes to read from start/end

    Returns:
        Tuple of (hash_value, error_message)
        hash_value is None if there was an error
    """
    try:
        file_size = os.path.getsize(file_path)

        hasher = hashlib.md5()

        # Include file size in hash
        hasher.update(str(file_size).encode('utf-8'))

        with open(file_path, 'rb') as f:
            # For small files, hash entire content
            if file_size <= MIN_SIZE_FOR_QUICK_HASH:
                hasher.update(f.read())
            else:
                # Read first chunk
                first_chunk = f.read(chunk_size)
                hasher.update(first_chunk)

                # Read last chunk (if file is large enough)
                if file_size > chunk_size * 2:
                    f.seek(-chunk_size, 2)  # Seek from end
                    last_chunk = f.read(chunk_size)
                    hasher.update(last_chunk)
                else:
                    # File is between MIN_SIZE and chunk_size*2
                    # Read remaining content
                    hasher.update(f.read())

        return hasher.hexdigest(), None

    except PermissionError:
        return None, "Permission denied"
    except FileNotFoundError:
        return None, "File not found"
    except OSError as e:
        return None, f"OS error: {e}"
    except Exception as e:
        return None, f"Unexpected error: {e}"


def compute_sha256(file_path: str, chunk_size: int = 65536) -> Tuple[Optional[str], Optional[str]]:
    """
    Compute SHA-256 hash of entire file content.

    Used for definitive duplicate confirmation after quick hash match.

    Args:
        file_path: Path to the file
        chunk_size: Read buffer size (default 64KB)

    Returns:
        Tuple of (hash_value, error_message)
        hash_value is None if there was an error
    """
    try:
        hasher = hashlib.sha256()

        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)

        return hasher.hexdigest(), None

    except PermissionError:
        return None, "Permission denied"
    except FileNotFoundError:
        return None, "File not found"
    except OSError as e:
        return None, f"OS error: {e}"
    except Exception as e:
        return None, f"Unexpected error: {e}"


def hash_file(file_path: str, compute_sha256_hash: bool = False) -> HashResult:
    """
    Hash a file with optional full SHA-256.

    Args:
        file_path: Path to the file
        compute_sha256_hash: Also compute SHA-256 (slower but definitive)

    Returns:
        HashResult with computed hashes and any errors
    """
    result = HashResult(
        file_path=file_path,
        file_size=0
    )

    try:
        result.file_size = os.path.getsize(file_path)
    except Exception as e:
        result.error = f"Could not get file size: {e}"
        return result

    # Compute quick hash
    quick_hash, error = compute_quick_hash(file_path)
    if error:
        result.error = error
        return result
    result.quick_hash = quick_hash

    # Optionally compute SHA-256
    if compute_sha256_hash:
        sha256, error = compute_sha256(file_path)
        if error:
            result.error = f"SHA-256 failed: {error}"
        else:
            result.sha256_hash = sha256

    return result


def files_are_duplicates(file1_path: str, file2_path: str) -> Tuple[bool, str]:
    """
    Check if two files are exact duplicates.

    Uses a multi-stage comparison:
    1. Compare file sizes (fast fail)
    2. Compare quick hashes (fast candidate confirmation)
    3. Compare SHA-256 hashes (definitive confirmation)

    Args:
        file1_path: Path to first file
        file2_path: Path to second file

    Returns:
        Tuple of (are_duplicates, reason/confidence)
    """
    try:
        # Stage 1: Size comparison
        size1 = os.path.getsize(file1_path)
        size2 = os.path.getsize(file2_path)

        if size1 != size2:
            return False, "Different file sizes"

        # Stage 2: Quick hash comparison
        qh1, err1 = compute_quick_hash(file1_path)
        qh2, err2 = compute_quick_hash(file2_path)

        if err1 or err2:
            return False, f"Hash error: {err1 or err2}"

        if qh1 != qh2:
            return False, "Quick hash mismatch"

        # Stage 3: SHA-256 comparison for definitive answer
        sha1, err1 = compute_sha256(file1_path)
        sha2, err2 = compute_sha256(file2_path)

        if err1 or err2:
            return False, f"SHA-256 error: {err1 or err2}"

        if sha1 == sha2:
            return True, "SHA-256 match confirmed"
        else:
            return False, "SHA-256 mismatch (hash collision in quick hash)"

    except Exception as e:
        return False, f"Comparison error: {e}"


def generate_composite_key(file_size: int, quick_hash: str) -> str:
    """
    Generate a composite key for grouping potential duplicates.

    This combines size and quick hash to create a unique identifier
    for duplicate group matching.

    Args:
        file_size: File size in bytes
        quick_hash: Quick hash value

    Returns:
        Composite key string
    """
    return f"{file_size}:{quick_hash}"


def parse_composite_key(key: str) -> Tuple[int, str]:
    """
    Parse a composite key back to size and hash.

    Args:
        key: Composite key string

    Returns:
        Tuple of (file_size, quick_hash)
    """
    parts = key.split(':', 1)
    return int(parts[0]), parts[1]


if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(description='File Hashing Utilities')
    parser.add_argument('file_path', help='Path to file to hash')
    parser.add_argument('--sha256', action='store_true', help='Also compute SHA-256')
    parser.add_argument('--compare', help='Compare with another file')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    if args.compare:
        are_dups, reason = files_are_duplicates(args.file_path, args.compare)
        if args.json:
            print(json.dumps({
                'file1': args.file_path,
                'file2': args.compare,
                'are_duplicates': are_dups,
                'reason': reason
            }, indent=2))
        else:
            print(f"Files are duplicates: {are_dups}")
            print(f"Reason: {reason}")
    else:
        result = hash_file(args.file_path, compute_sha256_hash=args.sha256)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"File: {result.file_path}")
            print(f"Size: {result.file_size:,} bytes")
            print(f"Quick Hash: {result.quick_hash}")
            if result.sha256_hash:
                print(f"SHA-256: {result.sha256_hash}")
            if result.error:
                print(f"Error: {result.error}")
