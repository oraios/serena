#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

// Test the Svelte language server
function testSvelteLSP() {
    console.log('🧪 Testing Svelte Language Server...');
    
    const serverProcess = spawn('svelteserver', ['--stdio'], {
        cwd: process.cwd()
    });
    
    let response = '';
    
    serverProcess.stdout.on('data', (data) => {
        response += data.toString();
        console.log('📤 Server response:', data.toString());
    });
    
    serverProcess.stderr.on('data', (data) => {
        console.error('❌ Server error:', data.toString());
    });
    
    serverProcess.on('close', (code) => {
        console.log(`🔚 Server process exited with code ${code}`);
        console.log('Full response:', response);
    });
    
    // Send initialize request
    const initRequest = {
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: {
            processId: process.pid,
            rootUri: `file://${process.cwd()}`,
            capabilities: {
                textDocument: {
                    synchronization: { didSave: true },
                    completion: { dynamicRegistration: true },
                    definition: { dynamicRegistration: true },
                    references: { dynamicRegistration: true },
                    documentSymbol: { 
                        dynamicRegistration: true,
                        hierarchicalDocumentSymbolSupport: true
                    }
                }
            }
        }
    };
    
    const message = JSON.stringify(initRequest);
    const header = `Content-Length: ${message.length}\r\n\r\n`;
    
    console.log('📨 Sending initialize request...');
    console.log('Header:', JSON.stringify(header));
    console.log('Message:', message);
    
    serverProcess.stdin.write(header + message);
    
    // Wait 3 seconds then exit
    setTimeout(() => {
        console.log('⏰ Test timeout, terminating...');
        serverProcess.kill();
        process.exit(0);
    }, 3000);
}

testSvelteLSP();