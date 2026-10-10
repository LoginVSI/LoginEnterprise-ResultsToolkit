// Syntax validation with Microsoft's parser; this is not a Mashup runtime.
const fs = require('node:fs');
const path = require('node:path');
const parserRoot = path.resolve(process.argv[2] || '.private/powerquery-validation');
const pq = require(path.join(parserRoot, 'node_modules/@microsoft/powerquery-parser'));
const files = process.argv.slice(3);
if (!files.length) files.push('adapters/powerbi/ResultsToolkit.pq');
(async () => {
  for (const file of files) {
    const task = await pq.TaskUtils.tryLexParse(pq.DefaultSettings, fs.readFileSync(file, 'utf8'));
    if (pq.TaskUtils.isError(task)) {
      const detail = task.error.innerError || task.error;
      console.error(`${file}: M syntax failed: ${detail.message}; line ${detail.positionStart?.lineNumber ?? 'unknown'}`);
      process.exitCode = 1;
    } else console.log(`${file}: Microsoft M parser passed`);
  }
})();
