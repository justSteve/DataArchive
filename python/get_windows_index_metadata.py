"""
Windows File Index Metadata Extractor
Retrieves file metadata from Windows Search Index for specified drive
"""

import win32com.client
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class WindowsIndexExtractor:
    """Extract file metadata from Windows Search Index"""

    def __init__(self, drive_letter: str = "E"):
        self.drive_letter = drive_letter.upper()
        self.connection = None
        self.recordset = None

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

    def get_indexed_files(self, max_results: int = 10000) -> List[Dict[str, Any]]:
        """
        Retrieve indexed file metadata for the specified drive
        """
        if not self.connection:
            if not self.connect_to_index():
                return []

        # SQL query to get file metadata from Windows Search Index
        query = f"""
        SELECT TOP {max_results}
            System.ItemPathDisplay,
            System.ItemName,
            System.ItemType,
            System.ItemFolderPathDisplay,
            System.Size,
            System.DateCreated,
            System.DateModified,
            System.DateAccessed,
            System.FileAttributes,
            System.FileExtension,
            System.Kind,
            System.MimeType,
            System.ItemUrl,
            System.ItemFolderNameDisplay,
            System.FileOwner,
            System.PerceivedType,
            System.FileDescription,
            System.CompanyName,
            System.FileVersion,
            System.ProductName,
            System.ProductVersion
        FROM SystemIndex 
        WHERE System.ItemPathDisplay LIKE '{self.drive_letter}:%'
        ORDER BY System.ItemPathDisplay
        """

        files = []
        try:
            self.recordset = win32com.client.Dispatch("ADODB.Recordset")
            self.recordset.Open(query, self.connection)

            count = 0
            while not self.recordset.EOF:
                try:
                    file_info = {}

                    # Extract all available fields
                    for i in range(self.recordset.Fields.Count):
                        field = self.recordset.Fields(i)
                        field_name = field.Name
                        field_value = field.Value

                        # Convert datetime objects to strings
                        if hasattr(field_value, 'strftime'):
                            field_value = field_value.isoformat()

                        file_info[field_name] = field_value

                    files.append(file_info)
                    count += 1

                    if count % 1000 == 0:
                        logger.info(f"Processed {count} files...")

                except Exception as e:
                    logger.warning(f"Error processing record: {e}")

                self.recordset.MoveNext()

            logger.info(f"Retrieved {len(files)} files from Windows Index")

        except Exception as e:
            logger.error(f"Error querying Windows Search Index: {e}")

        finally:
            if self.recordset:
                self.recordset.Close()

        return files

    def get_directory_structure(self, max_results: int = 10000) -> Dict[str, Any]:
        """
        Get directory structure with file counts and sizes
        """
        query = f"""
        SELECT 
            System.ItemFolderPathDisplay as FolderPath,
            COUNT(*) as FileCount,
            SUM(CAST(System.Size as BIGINT)) as TotalSize
        FROM SystemIndex 
        WHERE System.ItemPathDisplay LIKE '{self.drive_letter}:%'
        AND System.ItemType <> 'Directory'
        GROUP BY System.ItemFolderPathDisplay
        ORDER BY System.ItemFolderPathDisplay
        """

        directories = {}
        try:
            if not self.connection:
                if not self.connect_to_index():
                    return directories

            recordset = win32com.client.Dispatch("ADODB.Recordset")
            recordset.Open(query, self.connection)

            while not recordset.EOF:
                folder_path = recordset.Fields("FolderPath").Value or ""
                file_count = recordset.Fields("FileCount").Value or 0
                total_size = recordset.Fields("TotalSize").Value or 0

                directories[folder_path] = {
                    'file_count': file_count,
                    'total_size': total_size,
                    'size_mb': round(total_size / (1024 * 1024), 2) if total_size else 0
                }

                recordset.MoveNext()

            recordset.Close()
            logger.info(f"Retrieved {len(directories)} directories")

        except Exception as e:
            logger.error(f"Error getting directory structure: {e}")

        return directories

    def save_to_json(self, data: List[Dict], filename: str):
        """Save data to JSON file"""
        output_path = Path("output") / filename
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Data saved to {output_path}")

    def save_to_database(self, files: List[Dict], db_path: str = "output/windows_index.db"):
        """Save file metadata to SQLite database"""
        db_file = Path(db_path)
        db_file.parent.mkdir(exist_ok=True)

        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()

        # Create table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS indexed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT,
            name TEXT,
            type TEXT,
            folder_path TEXT,
            size INTEGER,
            date_created TEXT,
            date_modified TEXT,
            date_accessed TEXT,
            file_extension TEXT,
            kind TEXT,
            mime_type TEXT,
            file_owner TEXT,
            perceived_type TEXT,
            file_description TEXT,
            company_name TEXT,
            file_version TEXT,
            product_name TEXT,
            product_version TEXT,
            raw_metadata TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Insert data
        for file_info in files:
            cursor.execute("""
            INSERT INTO indexed_files (
                path, name, type, folder_path, size, date_created, date_modified,
                date_accessed, file_extension, kind, mime_type, file_owner,
                perceived_type, file_description, company_name, file_version,
                product_name, product_version, raw_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_info.get('System.ItemPathDisplay'),
                file_info.get('System.ItemName'),
                file_info.get('System.ItemType'),
                file_info.get('System.ItemFolderPathDisplay'),
                file_info.get('System.Size'),
                file_info.get('System.DateCreated'),
                file_info.get('System.DateModified'),
                file_info.get('System.DateAccessed'),
                file_info.get('System.FileExtension'),
                file_info.get('System.Kind'),
                file_info.get('System.MimeType'),
                file_info.get('System.FileOwner'),
                file_info.get('System.PerceivedType'),
                file_info.get('System.FileDescription'),
                file_info.get('System.CompanyName'),
                file_info.get('System.FileVersion'),
                file_info.get('System.ProductName'),
                file_info.get('System.ProductVersion'),
                json.dumps(file_info)
            ))

        conn.commit()
        conn.close()
        logger.info(f"Saved {len(files)} files to database: {db_file}")

    def generate_summary_report(self, files: List[Dict]) -> Dict[str, Any]:
        """Generate summary statistics"""
        if not files:
            return {}

        total_files = len(files)
        total_size = sum(f.get('System.Size', 0) or 0 for f in files)

        # File type distribution
        file_types = {}
        extensions = {}

        for f in files:
            file_type = f.get('System.PerceivedType', 'Unknown')
            extension = f.get('System.FileExtension', '').lower()

            file_types[file_type] = file_types.get(file_type, 0) + 1
            if extension:
                extensions[extension] = extensions.get(extension, 0) + 1

        # Top directories by file count
        directories = {}
        for f in files:
            folder = f.get('System.ItemFolderPathDisplay', '')
            if folder:
                directories[folder] = directories.get(folder, 0) + 1

        top_directories = sorted(
            directories.items(), key=lambda x: x[1], reverse=True)[:20]

        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_gb': round(total_size / (1024**3), 2),
            'file_types': dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True)),
            'top_extensions': dict(sorted(extensions.items(), key=lambda x: x[1], reverse=True)[:20]),
            'top_directories': dict(top_directories),
            'extraction_timestamp': datetime.now().isoformat()
        }

    def close(self):
        """Close connections"""
        if self.recordset:
            self.recordset.Close()
        if self.connection:
            self.connection.Close()


def main():
    """Main execution function"""
    print(f"Starting Windows Index extraction for drive E:")
    print(f"Timestamp: {datetime.now()}")

    extractor = WindowsIndexExtractor("E")

    try:
        # Get all indexed files
        print("\n1. Extracting file metadata from Windows Search Index...")
        files = extractor.get_indexed_files(
            max_results=50000)  # Adjust as needed

        if not files:
            print("No files found or unable to connect to Windows Search Index")
            return

        print(f"Found {len(files)} indexed files")

        # Get directory structure
        print("\n2. Analyzing directory structure...")
        directories = extractor.get_directory_structure()

        # Generate summary
        print("\n3. Generating summary report...")
        summary = extractor.generate_summary_report(files)

        # Save results
        print("\n4. Saving results...")

        # Save detailed file list
        extractor.save_to_json(
            files, f"drive_e_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        # Save directory structure
        extractor.save_to_json(
            directories, f"drive_e_directories_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        # Save summary
        extractor.save_to_json(
            summary, f"drive_e_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        # Save to database
        extractor.save_to_database(files)

        # Print summary
        print("\n" + "="*60)
        print("EXTRACTION SUMMARY")
        print("="*60)
        print(f"Total Files: {summary.get('total_files', 0):,}")
        print(f"Total Size: {summary.get('total_size_gb', 0)} GB")
        print(f"Unique Directories: {len(directories)}")

        print("\nTop File Types:")
        for file_type, count in list(summary.get('file_types', {}).items())[:10]:
            print(f"  {file_type}: {count:,}")

        print("\nTop Extensions:")
        for ext, count in list(summary.get('top_extensions', {}).items())[:10]:
            print(f"  {ext}: {count:,}")

        print("\nTop Directories by File Count:")
        for directory, count in list(summary.get('top_directories', {}).items())[:10]:
            print(f"  {directory}: {count:,} files")

        print("\n" + "="*60)
        print("Files saved to output/ directory")
        print("Database created: output/windows_index.db")

    except Exception as e:
        logger.error(f"Error during extraction: {e}")

    finally:
        extractor.close()


if __name__ == "__main__":
    main()
