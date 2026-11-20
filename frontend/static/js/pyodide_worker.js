/**
 * Pyodide Web Worker for In-Browser Code Execution.
 * Runs 100% locally in the browser's client-side sandbox.
 * Zero server-side code execution.
 */

let pyodide = null;
let isInitializing = false;

async function initPyodideWorker() {
  if (pyodide) return;
  if (isInitializing) return;
  isInitializing = true;

  try {
    importScripts('https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js');
    pyodide = await loadPyodide({
      indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/',
    });
    postMessage({ type: 'ready' });
  } catch (err) {
    postMessage({ type: 'error', error: 'Failed to load Pyodide runtime: ' + err.message });
  } finally {
    isInitializing = false;
  }
}

self.onmessage = async function(e) {
  const { type, code, id } = e.data;

  if (type === 'init') {
    await initPyodideWorker();
    return;
  }

  if (type === 'run') {
    if (!pyodide) {
      await initPyodideWorker();
    }

    if (!pyodide) {
      postMessage({ type: 'result', id, success: false, error: 'Pyodide runtime not ready' });
      return;
    }

    let stdout = '';
    let stderr = '';

    pyodide.setStdout({
      batched: (msg) => { stdout += msg + '\n'; }
    });
    pyodide.setStderr({
      batched: (msg) => { stderr += msg + '\n'; }
    });

    const t0 = performance.now();
    try {
      const result = await pyodide.runPythonAsync(code);
      const executionMs = Math.round(performance.now() - t0);
      let returnVal = '';
      if (result !== undefined && result !== null) {
        returnVal = String(result);
      }
      postMessage({
        type: 'result',
        id,
        success: true,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        result: returnVal,
        executionMs,
      });
    } catch (err) {
      const executionMs = Math.round(performance.now() - t0);
      postMessage({
        type: 'result',
        id,
        success: false,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        error: err.message,
        executionMs,
      });
    }
  }
};
