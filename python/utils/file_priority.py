"""
File Priority Classifier

Classifies files by archival priority:
- high: Critical archival files (databases, documents, custom work)
- medium: Potentially important (configs, scripts, logs with content)
- low: Recoverable or low-value (framework code, binaries)
- skip: Never archive (cache, temp, logs, node_modules)

Priority is determined by:
1. File extension
2. Path patterns (subdirectory names)
3. File size (tiny files in framework locations = skip)
"""

from pathlib import Path
from typing import Tuple

# High-value extensions - always archive
HIGH_PRIORITY_EXTENSIONS = {
    # Databases
    '.mdf', '.ldf', '.bak', '.sql', '.sqlite', '.db',
    # Email archives
    '.pst', '.ost', '.eml', '.msg',
    # Documents
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.pdf',
    '.odt', '.ods', '.odp',
    # Design files
    '.dwg', '.dxf', '.psd', '.ai', '.indd', '.sketch',
    # CAD/Engineering
    '.sldprt', '.sldasm', '.step', '.iges',
    # Archives
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
    # Source control bundles
    '.bundle',
}

# Medium priority - might be important
MEDIUM_PRIORITY_EXTENSIONS = {
    # Config files (might be customized)
    '.config', '.xml', '.json', '.yaml', '.yml', '.toml', '.ini', '.conf',
    # Scripts (might be custom)
    '.sh', '.bat', '.ps1', '.py', '.rb', '.pl',
    # Web content
    '.html', '.htm', '.aspx', '.php', '.jsp', '.cshtml',
    # Code (might be custom)
    '.cs', '.java', '.cpp', '.c', '.h', '.go', '.rs',
    # Stylesheets
    '.css', '.scss', '.sass', '.less',
    # Text files
    '.txt', '.md', '.csv', '.log',
    # Media (potentially custom)
    '.mp4', '.avi', '.mov', '.mp3', '.wav',
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.bmp',
}

# Low priority - recoverable or framework code
LOW_PRIORITY_EXTENSIONS = {
    # JavaScript (usually framework/library)
    '.js', '.ts', '.jsx', '.tsx',
    # Minified/compiled
    '.min.js', '.min.css', '.map',
    # Compiled binaries
    '.dll', '.exe', '.so', '.dylib',
    # Object files
    '.o', '.obj', '.pyc', '.pyo',
}

# Path patterns that indicate files should be skipped
SKIP_PATH_PATTERNS = [
    # Cache directories
    'cache', 'Cache', 'CACHE',
    'cached', 'Cached',
    # Temp directories
    'temp', 'Temp', 'TEMP', 'tmp', 'TMP',
    'temporary', 'Temporary',
    # Log directories (archive individual logs via extension, not log dirs)
    'logs', 'Logs', 'LOGS',
    # Framework/dependency directories
    'node_modules',
    'bower_components',
    'vendor',
    'packages',
    '.git',
    '.svn',
    '__pycache__',
    'venv', '.venv', 'virtualenv',
    # Browser caches
    'User Data/Default/Cache',
    'User Data/Default/Code Cache',
    'Profiles/*/cache2',
    'Profiles/*/startupCache',
    # Windows Defender
    'Windows Defender',
    # Package caches
    'NuGet/Cache',
    'npm-cache',
    'pip/cache',
]

# Path patterns for medium priority (might contain custom work)
MEDIUM_PATH_PATTERNS = [
    'inetpub',
    'wwwroot',
    'htdocs',
    'public_html',
    'MySQL',
    'PostgreSQL',
    'SQL Server',
]

# Path patterns for high priority
HIGH_PATH_PATTERNS = [
    'Documents',
    'Desktop',
    'Downloads',
    'Projects',
    'Backups',
    'Archives',
]


def classify_file_priority(file_path: str, size_bytes: int) -> str:
    """
    Classify a file's archival priority

    Args:
        file_path: Relative or absolute file path
        size_bytes: File size in bytes

    Returns:
        Priority level: 'high', 'medium', 'low', or 'skip'
    """
    path = Path(file_path)
    extension = path.suffix.lower()
    path_str = str(path).replace('\\', '/')

    # Check if path contains skip patterns
    for pattern in SKIP_PATH_PATTERNS:
        if f'/{pattern}/' in f'/{path_str}/' or path_str.startswith(f'{pattern}/'):
            return 'skip'

    # Extension-based classification
    if extension in HIGH_PRIORITY_EXTENSIONS:
        return 'high'

    # Executables and DLLs - low priority unless in specific locations
    if extension in {'.exe', '.dll', '.so', '.dylib'}:
        # Check if in a high-value location
        for pattern in HIGH_PATH_PATTERNS:
            if pattern.lower() in path_str.lower():
                return 'medium'  # Executables in user docs might be important
        return 'low'  # Framework/system executables

    # JavaScript/TypeScript - usually framework unless in specific locations
    if extension in {'.js', '.ts', '.jsx', '.tsx'}:
        # In node_modules or similar = skip (handled above)
        # In custom project locations = medium
        if any(p.lower() in path_str.lower() for p in ['src/', 'lib/', 'scripts/']):
            return 'medium'
        # Minified = low priority
        if '.min.' in path.name.lower():
            return 'low'
        return 'low'  # Default for JS/TS

    # Check for high-priority path patterns
    for pattern in HIGH_PATH_PATTERNS:
        if pattern.lower() in path_str.lower():
            if extension in MEDIUM_PRIORITY_EXTENSIONS:
                return 'high'  # Configs in user docs = elevated
            return 'medium'

    # Check for medium-priority path patterns (like inetpub)
    for pattern in MEDIUM_PATH_PATTERNS:
        if pattern.lower() in path_str.lower():
            if extension in MEDIUM_PRIORITY_EXTENSIONS:
                return 'high'  # Web content configs
            return 'medium'

    # Medium priority extensions
    if extension in MEDIUM_PRIORITY_EXTENSIONS:
        # Small files in deep paths might be framework
        if size_bytes < 1024 and len(path.parts) > 5:
            return 'low'
        return 'medium'

    # Low priority extensions
    if extension in LOW_PRIORITY_EXTENSIONS:
        return 'low'

    # Unknown extensions - medium by default
    return 'medium'


def should_skip_file(file_path: str, size_bytes: int) -> bool:
    """
    Determine if a file should be skipped entirely

    Args:
        file_path: File path
        size_bytes: File size

    Returns:
        True if file should be skipped
    """
    return classify_file_priority(file_path, size_bytes) == 'skip'


def get_priority_stats(files: list) -> dict:
    """
    Get priority distribution statistics

    Args:
        files: List of (path, size) tuples

    Returns:
        Dictionary with counts and sizes per priority
    """
    stats = {
        'high': {'count': 0, 'total_bytes': 0},
        'medium': {'count': 0, 'total_bytes': 0},
        'low': {'count': 0, 'total_bytes': 0},
        'skip': {'count': 0, 'total_bytes': 0},
    }

    for path, size in files:
        priority = classify_file_priority(path, size)
        stats[priority]['count'] += 1
        stats[priority]['total_bytes'] += size

    return stats


if __name__ == '__main__':
    # Test cases
    test_files = [
        ('/mnt/d/Users/Steve/Documents/report.docx', 50000, 'high'),
        ('/mnt/d/inetpub/wwwroot/index.html', 2000, 'high'),
        ('/mnt/d/ProgramData/MySQL/backup.sql', 1000000, 'high'),
        ('/mnt/d/node_modules/express/lib/router.js', 5000, 'skip'),
        ('/mnt/d/Windows/System32/kernel32.dll', 100000, 'low'),
        ('/mnt/d/Users/Steve/AppData/Local/Temp/tmp123.txt', 100, 'skip'),
        ('/mnt/d/inetpub/logs/access.log', 50000, 'skip'),
        ('/mnt/d/Custom/config.json', 500, 'medium'),
    ]

    print("File Priority Classification Tests:\n")
    for path, size, expected in test_files:
        priority = classify_file_priority(path, size)
        status = "✓" if priority == expected else "✗"
        print(f"{status} {path}")
        print(f"  Expected: {expected}, Got: {priority}")
        print()
