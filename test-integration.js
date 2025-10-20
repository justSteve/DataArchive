/**
 * Quick integration test for Python bridge
 * Run with: node test-integration.js
 */

const { PythonBridge } = require('./dist/services/PythonBridge');
const path = require('path');

async function testPythonBridge() {
  console.log('='.repeat(60));
  console.log('Python-TypeScript Integration Test');
  console.log('='.repeat(60));
  console.log('');

  const bridge = new PythonBridge();

  try {
    // Test 1: Validate drive (placeholder for now)
    console.log('Test 1: Drive Validation');
    console.log('-'.repeat(60));
    const validation = await bridge.validateDrive('/mnt/c');
    console.log('✓ Validation result:', JSON.stringify(validation, null, 2));
    console.log('');

    // Test 2: Get drive info (placeholder for now)
    console.log('Test 2: Get Drive Info');
    console.log('-'.repeat(60));
    const driveInfo = await bridge.getDriveInfo('/mnt/c');
    console.log('✓ Drive info:', JSON.stringify(driveInfo, null, 2));
    console.log('');

    // Test 3: Detect OS (placeholder for now)
    console.log('Test 3: OS Detection');
    console.log('-'.repeat(60));
    const osInfo = await bridge.detectOS('/mnt/c');
    console.log('✓ OS info:', JSON.stringify(osInfo, null, 2));
    console.log('');

    console.log('='.repeat(60));
    console.log('✓ All tests passed!');
    console.log('='.repeat(60));
    console.log('');
    console.log('Next steps:');
    console.log('  1. Create output directory: mkdir -p output');
    console.log('  2. Test real scan: Use the API endpoint POST /api/scans/start');
    console.log('  3. Start API server: npm run api');
    console.log('');

  } catch (error) {
    console.error('✗ Test failed:', error.message);
    console.error('');
    console.error('Error details:', error);
    process.exit(1);
  }
}

testPythonBridge();
