// Separate fallback policy so every failure route can be checked without a browser.
export async function withCpuFallback(prepare, execute, report) {
  let accelerated = false;
  try {accelerated = await prepare();} catch (_) {}
  if (!accelerated) report();
  try {return await execute(accelerated ? 'wasm' : 'cpu');}
  catch (error) {
    if (!accelerated) throw error;
    report();
    return execute('cpu');
  }
}
