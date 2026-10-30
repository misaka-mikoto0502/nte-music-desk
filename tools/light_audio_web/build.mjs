import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
const here = path.dirname(fileURLToPath(import.meta.url));
const modules = path.resolve(process.env.NTE_LIGHT_NODE_MODULES || path.join(here, 'node_modules'));
const esbuild = (await import(pathToFileURL(path.join(modules, 'esbuild/lib/main.js')))).default;
if (process.argv[2] === '--benchmark') {
  if (!process.argv[3]) throw new Error('Pass the generated benchmark folder');
  const work = path.resolve(here, '../../.build');fs.mkdirSync(work,{recursive:true});
  const runner = path.join(work,'light-audio-benchmark.cjs');
  await esbuild.build({entryPoints:[path.join(here,'benchmark_runner.js')],outfile:runner,
    bundle:true,platform:'node',format:'cjs',mainFields:['module','main'],nodePaths:[modules]});
  const run=spawnSync(process.execPath,[runner,path.resolve(process.argv[3]),path.join(modules,'@spotify/basic-pitch/model')],{stdio:'inherit'});
  process.exit(run.status ?? 1);
}
const target = path.resolve(here, '../../src/nte_music_desk/assets/light_audio');
fs.mkdirSync(target, {recursive: true});
const included = new Set();
for (const name of ['worker', 'main']) {
  const result = await esbuild.build({entryPoints: [path.join(here, name + '.js')], outfile: path.join(target, name + '.js'),
    bundle: true, minify: true, platform: 'browser', target: ['es2020'], legalComments: 'eof',
    nodePaths: [modules], metafile: true});
  for (const input of Object.keys(result.metafile.inputs)) {
    let folder = path.dirname(path.resolve(input));
    while (folder.includes('node_modules')) {
      if (fs.existsSync(path.join(folder, 'package.json'))) {included.add(folder); break;}
      folder = path.dirname(folder);
    }
  }
}
const pitch = path.join(modules, '@spotify/basic-pitch');
for (const file of ['model.json', 'group1-shard1of1.bin']) fs.copyFileSync(path.join(pitch, 'model', file), path.join(target, file));
for (const file of ['index.html', 'style.css']) fs.copyFileSync(path.join(here, file), path.join(target, file));
for (const file of ['tfjs-backend-wasm.wasm', 'tfjs-backend-wasm-simd.wasm']) {
  fs.copyFileSync(path.join(modules, '@tensorflow/tfjs-backend-wasm/dist', file), path.join(target, file));
}
let notices = 'NTE Music Desk lightweight transcription\nCPU in an existing browser, single-thread WebAssembly with plain JS fallback.\nNo Python, Node, GPU runtime or browser engine redistributed.\n\n';
for (const folder of [...included].sort()) {
  const pkg = JSON.parse(fs.readFileSync(path.join(folder, 'package.json')));
  if (!['Apache-2.0', 'MIT', 'ISC', 'BSD-3-Clause', 'BSD-2-Clause'].includes(pkg.license)) throw new Error(`Unreviewed license: ${pkg.name} ${pkg.license}`);
  notices += `\n======== ${pkg.name}@${pkg.version} (${pkg.license}) ========\n`;
  if (pkg.repository) notices += JSON.stringify(pkg.repository) + '\n';
  let found = false;
  for (const file of fs.readdirSync(folder)) {
    if (/^(LICENSE|LICENCE|NOTICE|COPYING)(\..*)?$/i.test(file) && fs.statSync(path.join(folder, file)).isFile()) {
      notices += fs.readFileSync(path.join(folder, file), 'utf8') + '\n'; found = true;
    }
  }
  if (!found && pkg.name === 'seedrandom') {
    const readme = fs.readFileSync(path.join(folder, 'README.md'), 'utf8');
    const start = readme.indexOf('LICENSE (MIT)');
    if (start < 0) throw new Error('seedrandom license not found');
    notices += readme.slice(start); found = true;
  }
  if (!found && pkg.license === 'Apache-2.0') notices += fs.readFileSync(path.join(pitch, 'LICENSE'), 'utf8') + '\n';
  else if (!found) throw new Error(`Missing license text: ${pkg.name}`);
}
notices += '\nModel: @spotify/basic-pitch 1.0.1/model, unchanged Spotify files under Apache-2.0.\nSource: https://github.com/spotify/basic-pitch-ts\nCopyright 2022 Spotify AB.\nTensorFlow.js source: https://github.com/tensorflow/tfjs\nGoogle LLC and TensorFlow.js contributors.\n';
notices += '\n' + fs.readFileSync(path.join(here,'wasm-notices.txt'),'utf8');
fs.writeFileSync(path.join(target, 'licenses.txt'), notices);
const files = {};
let total = 0;
for (const file of ['index.html', 'style.css', 'main.js', 'worker.js', 'model.json', 'group1-shard1of1.bin', 'licenses.txt', 'tfjs-backend-wasm.wasm', 'tfjs-backend-wasm-simd.wasm']) {
  const data = fs.readFileSync(path.join(target, file)); total += data.length;
  files[file] = crypto.createHash('sha256').update(data).digest('hex');
}
if (total > 4_500_000) throw new Error(`Component over size budget: ${total}`);
fs.writeFileSync(path.join(target, 'manifest.json'), JSON.stringify({schema: 'nte-light-web-v1', bytes: total,
  versions: {'basic-pitch': '1.0.1', 'tensorflow.js': '3.21.0'}, files}, null, 2) + '\n');
console.log(JSON.stringify({bytes: total, packages: included.size, target}, null, 2));
