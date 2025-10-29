#!/usr/bin/env python3
"""
Web UI for interactive file selection and archival

Usage:
    python archive_ui.py
    
Then navigate to: http://localhost:5000
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

from core.logger import get_logger
from core.database import Database

logger = get_logger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'data-archive-secret-key'
socketio = SocketIO(app)

# Initialize database
db = Database()


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/api/scans')
def list_scans():
    """List all scan sessions"""
    try:
        with db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    s.scan_id,
                    s.scan_start,
                    s.scan_end,
                    s.file_count,
                    s.total_size_bytes,
                    s.mount_point,
                    d.model,
                    d.serial_number,
                    o.os_name
                FROM scans s
                JOIN drives d ON s.drive_id = d.drive_id
                LEFT JOIN os_info o ON s.scan_id = o.scan_id
                WHERE s.status = 'COMPLETE'
                ORDER BY s.scan_start DESC
            """)
            
            scans = []
            for row in cursor:
                scans.append({
                    'scan_id': row['scan_id'],
                    'scan_date': row['scan_start'],
                    'model': row['model'],
                    'serial': row['serial_number'],
                    'mount_point': row['mount_point'],
                    'file_count': row['file_count'],
                    'size_gb': row['total_size_bytes'] / (1024**3) if row['total_size_bytes'] else 0,
                    'os_name': row['os_name'] or 'Unknown'
                })
            
            return jsonify(scans)
    except Exception as e:
        logger.error(f"Error listing scans: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tree/<int:scan_id>')
def get_tree(scan_id):
    """Get file tree for a scan"""
    try:
        tree = db.get_file_tree(scan_id, max_depth=3)
        
        # Convert to jsTree format
        def convert_node(path, node):
            children = []
            for child_name, child_node in node.get('children', {}).items():
                children.append(convert_node(f"{path}/{child_name}", child_node))
            
            return {
                'id': path,
                'text': f"{Path(path).name} ({node['file_count']} files, {node['size'] / (1024**2):.1f} MB)",
                'children': children,
                'data': {
                    'path': path,
                    'file_count': node['file_count'],
                    'size': node['size'],
                    'state': 'blank'  # blank | include | exclude
                }
            }
        
        # Build root nodes
        jstree_data = []
        for root_name, root_node in tree.items():
            jstree_data.append(convert_node(root_name, root_node))
        
        return jsonify(jstree_data)
    except Exception as e:
        logger.error(f"Error getting tree: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/archive', methods=['POST'])
def start_archive():
    """Start archival process"""
    try:
        data = request.json
        scan_id = data.get('scan_id')
        selected = data.get('selected', [])
        excluded = data.get('excluded', [])
        
        logger.info(f"Archive requested for scan {scan_id}")
        logger.info(f"Selected: {len(selected)} paths")
        logger.info(f"Excluded: {len(excluded)} paths")
        
        # TODO: Implement actual copy logic
        # For now, just acknowledge the request
        
        return jsonify({
            'status': 'started',
            'scan_id': scan_id,
            'message': 'Archive process will be implemented in next phase'
        })
    except Exception as e:
        logger.error(f"Error starting archive: {e}")
        return jsonify({'error': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info("Client connected")
    emit('connected', {'message': 'Connected to archive server'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnect"""
    logger.info("Client disconnected")


def main():
    """Main entry point"""
    logger.info("="*60)
    logger.info("DATA ARCHIVE SYSTEM - Web UI")
    logger.info("="*60)
    logger.info("Starting web server...")
    logger.info("Navigate to: http://localhost:5000")
    logger.info("Press Ctrl+C to stop")
    logger.info("="*60)
    
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    except Exception as e:
        logger.error(f"Error running web server: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
