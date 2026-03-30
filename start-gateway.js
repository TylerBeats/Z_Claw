const { spawn } = require('child_process');
const proc = spawn('openclaw', ['gateway', 'run'], { stdio: 'inherit', shell: true });
proc.on('exit', (code) => process.exit(code ?? 0));
