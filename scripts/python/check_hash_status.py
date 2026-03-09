import sqlite3

conn = sqlite3.connect('output/archive.db')
c = conn.cursor()

# Total files
c.execute('SELECT COUNT(*) FROM files WHERE scan_id = 3')
print(f'Total files: {c.fetchone()[0]:,}')

# Files with hashes
c.execute('SELECT COUNT(DISTINCT file_id) FROM file_hashes WHERE scan_id = 3 AND hash_type = "quick_hash"')
print(f'Files with hashes: {c.fetchone()[0]:,}')

# Files without hashes
c.execute('''
    SELECT f.file_id, f.path
    FROM files f
    WHERE f.scan_id = 3
    AND NOT EXISTS (SELECT 1 FROM file_hashes WHERE file_id = f.file_id AND hash_type = 'quick_hash')
''')
missing = c.fetchall()
print(f'\nFiles without hashes: {len(missing)}')
for file_id, path in missing:
    print(f'  {file_id}: {path}')

# Recent hash timestamps
c.execute('SELECT computed_at FROM file_hashes WHERE scan_id = 3 AND hash_type = "quick_hash" ORDER BY computed_at DESC LIMIT 1')
print(f'\nMost recent hash: {c.fetchone()[0]}')

c.execute('SELECT computed_at FROM file_hashes WHERE scan_id = 3 AND hash_type = "quick_hash" ORDER BY computed_at ASC LIMIT 1')
print(f'Oldest hash: {c.fetchone()[0]}')

conn.close()
