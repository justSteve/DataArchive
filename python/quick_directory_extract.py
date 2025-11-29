"""
Quick Directory Structure Extractor using Windows Search Index
Focuses on getting directory tree and file counts quickly
"""

import win32com.client
import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class QuickDirectoryExtractor:
    """Fast directory structure extraction from Windows Search Index"""

    def __init__(self, drive_letter: str = "E"):
        self.drive_letter = drive_letter.upper()
        self.connection = None

    def connect_to_index(self):
        """Connect to Windows Search Index"""
        try:
            self.connection = win32com.client.Dispatch("ADODB.Connection")
            self.connection.Open(
                "Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
            logger.info("Connected to Windows Search Index")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Windows Search Index: {e}")
            return False

    def get_directory_tree(self):
        """Get complete directory structure with file counts and sizes"""
        if not self.connect_to_index():
            return {}

        # Query for directory summary
        query = f"""
        SELECT 
            System.ItemFolderPathDisplay as FolderPath,
            System.FileExtension as Extension,
            COUNT(*) as FileCount,
            SUM(CAST(ISNULL(System.Size, 0) as BIGINT)) as TotalSize,
            MIN(System.DateCreated) as OldestFile,
            MAX(System.DateModified) as NewestFile
        FROM SystemIndex 
        WHERE System.ItemPathDisplay LIKE '{self.drive_letter}:%'
        AND System.ItemType <> 'Directory'
        GROUP BY System.ItemFolderPathDisplay, System.FileExtension
        ORDER BY System.ItemFolderPathDisplay, System.FileExtension
        """

        directory_tree = defaultdict(lambda: {
            'total_files': 0,
            'total_size': 0,
            'extensions': {},
            'oldest_file': None,
            'newest_file': None
        })

        try:
            recordset = win32com.client.Dispatch("ADODB.Recordset")
            recordset.Open(query, self.connection)

            while not recordset.EOF:
                folder_path = recordset.Fields("FolderPath").Value or "Unknown"
                extension = recordset.Fields(
                    "Extension").Value or "no_extension"
                file_count = recordset.Fields("FileCount").Value or 0
                total_size = recordset.Fields("TotalSize").Value or 0
                oldest = recordset.Fields("OldestFile").Value
                newest = recordset.Fields("NewestFile").Value

                # Update directory info
                dir_info = directory_tree[folder_path]
                dir_info['total_files'] += file_count
                dir_info['total_size'] += total_size
                dir_info['extensions'][extension] = file_count

                # Track oldest/newest files
                if oldest:
                    oldest_str = oldest.isoformat() if hasattr(
                        oldest, 'isoformat') else str(oldest)
                    if not dir_info['oldest_file'] or oldest_str < dir_info['oldest_file']:
                        dir_info['oldest_file'] = oldest_str

                if newest:
                    newest_str = newest.isoformat() if hasattr(
                        newest, 'isoformat') else str(newest)
                    if not dir_info['newest_file'] or newest_str > dir_info['newest_file']:
                        dir_info['newest_file'] = newest_str

                recordset.MoveNext()

            recordset.Close()
            logger.info(f"Processed {len(directory_tree)} directories")

        except Exception as e:
            logger.error(f"Error extracting directory tree: {e}")

        finally:
            if self.connection:
                self.connection.Close()

        return dict(directory_tree)

    def create_hierarchical_tree(self, flat_dirs):
        """Convert flat directory list to hierarchical tree structure"""
        tree = {}

        for dir_path, info in flat_dirs.items():
            if not dir_path or dir_path == "Unknown":
                continue

            # Split path into parts
            path_parts = Path(dir_path).parts

            # Navigate/create tree structure
            current = tree
            for part in path_parts:
                if part not in current:
                    current[part] = {
                        'subdirs': {},
                        'info': {
                            'total_files': 0,
                            'total_size': 0,
                            'extensions': {},
                            'direct_files': 0,
                            'direct_size': 0
                        }
                    }
                current = current[part]['subdirs']

            # Add the directory info to the leaf
            # Navigate back to set the info
            current = tree
            for part in path_parts[:-1]:
                current = current[part]['subdirs']

            if path_parts:
                leaf_name = path_parts[-1]
                if leaf_name in current:
                    current[leaf_name]['info'].update({
                        'direct_files': info['total_files'],
                        'direct_size': info['total_size'],
                        'extensions': info['extensions'],
                        'oldest_file': info.get('oldest_file'),
                        'newest_file': info.get('newest_file')
                    })

        return tree

    def print_tree_summary(self, flat_dirs):
        """Print a summary of the directory structure"""
        total_dirs = len(flat_dirs)
        total_files = sum(d['total_files'] for d in flat_dirs.values())
        total_size = sum(d['total_size'] for d in flat_dirs.values())

        print("\n" + "="*60)
        print(f"DRIVE {self.drive_letter}: DIRECTORY STRUCTURE SUMMARY")
        print("="*60)
        print(f"Total Directories: {total_dirs:,}")
        print(f"Total Files: {total_files:,}")
        print(f"Total Size: {total_size / (1024**3):.2f} GB")

        # Top directories by file count
        top_dirs = sorted(flat_dirs.items(),
                          key=lambda x: x[1]['total_files'], reverse=True)[:15]

        print(f"\nTop Directories by File Count:")
        print("-" * 80)
        for dir_path, info in top_dirs:
            size_mb = info['total_size'] / (1024**2)
            print(
                f"{info['total_files']:>6,} files | {size_mb:>8.1f} MB | {dir_path}")

        # File extension summary across all directories
        all_extensions = defaultdict(int)
        for dir_info in flat_dirs.values():
            for ext, count in dir_info['extensions'].items():
                all_extensions[ext] += count

        top_extensions = sorted(all_extensions.items(),
                                key=lambda x: x[1], reverse=True)[:20]

        print(f"\nTop File Extensions:")
        print("-" * 40)
        for ext, count in top_extensions:
            ext_display = ext if ext != "no_extension" else "(no extension)"
            print(f"{count:>8,} | {ext_display}")

        print("="*60)


def main():
    """Main execution"""
    print("Quick Directory Structure Extraction")
    print("="*50)

    # You can change the drive letter here
    drive_letter = "E"  # Change this to your target drive

    extractor = QuickDirectoryExtractor(drive_letter)

    print(f"Extracting directory structure for drive {drive_letter}:")
    print("This uses Windows Search Index for fast results...")

    # Get directory structure
    directory_data = extractor.get_directory_tree()

    if not directory_data:
        print("No data retrieved. Make sure:")
        print("1. Drive E: is connected and indexed by Windows")
        print("2. Windows Search service is running")
        print("3. You're running this on Windows (not WSL)")
        return

    # Save raw data
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # Save flat directory structure
    with open(output_dir / f"drive_{drive_letter}_directories_{timestamp}.json", 'w') as f:
        json.dump(directory_data, f, indent=2)

    # Create and save hierarchical tree
    hierarchical_tree = extractor.create_hierarchical_tree(directory_data)
    with open(output_dir / f"drive_{drive_letter}_tree_{timestamp}.json", 'w') as f:
        json.dump(hierarchical_tree, f, indent=2)

    # Print summary
    extractor.print_tree_summary(directory_data)

    print(f"\nData saved to:")
    print(f"  - output/drive_{drive_letter}_directories_{timestamp}.json")
    print(f"  - output/drive_{drive_letter}_tree_{timestamp}.json")


if __name__ == "__main__":
    main()
