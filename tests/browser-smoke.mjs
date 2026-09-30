import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fixtures = path.join(root, 'artifacts/fixtures'), output = path.join(root, 'artifacts/static');
fs.mkdirSync(output, {recursive:true});
const browser = await chromium.launch({headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});
const checks = [], errors = [];
async function openTool(page,id) {const card=page.locator('#tool-'+id);if(!await card.evaluate(el=>el.open))await card.locator('summary').click();}
async function save(page,selector,name) {const pending=page.waitForEvent('download');await page.locator(selector).click();const item=await pending;assert.equal(await item.failure(),null);await item.saveAs(path.join(output,name));}
async function inspect(page,name) {return page.evaluate(async bytes=>{const doc=await window.PDFLib.PDFDocument.load(new Uint8Array(bytes));return doc.getPages().map(page=>({rotation:page.getRotation().angle,box:page.getCropBox()}));},[...fs.readFileSync(path.join(output,name))]);}
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});
  page.on('pageerror',error=>errors.push(error.message));
  let posted=0;page.on('request',request=>{if(request.method()==='POST'&&request.url().includes('/api/'))posted++;});
  await page.goto(process.env.MODUPDF_STATIC_URL || 'http://127.0.0.1:8769');
  await page.locator('#connectionStatus.local').waitFor();assert.equal(await page.locator('.card[open]').count(),0);
  await page.locator('#orgFile').setInputFiles([path.join(fixtures,'a.pdf'),path.join(fixtures,'b.pdf')]);await page.waitForFunction(()=>document.querySelectorAll('.page').length===5);
  await page.locator('.page').first().click();await page.locator('[data-org="rotate"]').click();await page.locator('[data-org="duplicate"]').click();
  await page.locator('.page').last().dragTo(page.locator('.page').first(),{targetPosition:{x:5,y:50}});
  await save(page,'#saveOrg','organized.pdf');const organized=await inspect(page,'organized.pdf');assert.equal(organized.length,6);assert.deepEqual(organized.map(page=>page.rotation),[0,90,90,0,0,0]);checks.push('static organizer, drag/drop, rotation, duplication and download');
  for(const [tab,id,files,fields,name,count] of [
    ['organizar','merge',['a.pdf','b.pdf'],{},'merge.pdf',5],['organizar','split',['a.pdf'],{pages:'3,1'},'split.pdf',2],
    ['organizar','remove',['a.pdf'],{pages:'2'},'remove.pdf',2],['organizar','rotate',['a.pdf'],{},'rotate.pdf',3],
    ['otimizar','compress',['a.pdf'],{target_mb:'0.01'},'compressed.pdf',3],['otimizar','repair',['a.pdf'],{},'repair.pdf',3],
    ['otimizar','scan',['image.png'],{},'scan.pdf',1],['converter','images',['image.png'],{},'images.pdf',1],
    ['converter','pimg',['a.pdf'],{},'images.zip',null],['editar','nums',['a.pdf'],{start:'7'},'numbered.pdf',3],
    ['editar','watermark',['a.pdf'],{text:'LOCAL WATERMARK'},'watermark.pdf',3],['editar','crop',['a.pdf'],{margin:'20'},'cropped.pdf',3]
  ]) {
    await page.locator('[data-tab="'+tab+'"]').click();await openTool(page,id);await page.locator('#'+id+'-file').setInputFiles(files.map(file=>path.join(fixtures,file)));
    for(const [key,value] of Object.entries(fields))await page.locator('#'+id+'-'+key).fill(value);
    await save(page,'[data-run="'+id+'"]',name);if(count!==null)assert.equal((await inspect(page,name)).length,count);checks.push('static '+id+' process/download');
  }
  assert.ok(fs.statSync(path.join(output,'compressed.pdf')).size<=fs.statSync(path.join(fixtures,'a.pdf')).size);
  const crop=await inspect(page,'cropped.pdf');assert.equal(Math.round(crop[0].box.width),380);
  const zip=await page.evaluate(async bytes=>Object.keys((await window.JSZip.loadAsync(new Uint8Array(bytes))).files),[...fs.readFileSync(path.join(output,'images.zip'))]);assert.equal(zip.length,3);
  await page.locator('[data-tab="organizar"]').click();await openTool(page,'split');await page.locator('#split-mode').selectOption('individual');await save(page,'[data-run="split"]','split.zip');
  const split=await page.evaluate(async bytes=>Object.keys((await window.JSZip.loadAsync(new Uint8Array(bytes))).files),[...fs.readFileSync(path.join(output,'split.zip'))]);assert.equal(split.length,2);checks.push('static split into individual ZIP');
  await page.locator('[data-tab="seguranca"]').click();await openTool(page,'protect');assert.equal(await page.locator('[data-run="protect"]').isDisabled(),true);
  for(const [tab,id] of [['editar','replace-text'],['editar','edit'],['editar','newforms'],['editar','forms'],['seguranca','redact']]) {
    await page.locator('[data-tab="'+tab+'"]').click();await openTool(page,id);
    assert.equal(await page.locator('[data-run="'+id+'"]').isDisabled(),true,id+' requires an API to save');
    assert.equal(await page.locator('#'+id+'-state').textContent(),'Servidor necessário');
    assert.equal(await page.locator('#'+id+'-availability').isVisible(),true);
  }
  await page.locator('[data-tab="otimizar"]').click();assert.equal(await page.locator('[data-run="ocr"]').isDisabled(),true);assert.equal(await page.locator('#scan-run_ocr').isDisabled(),true);checks.push('server-only operations honestly disabled');
  assert.equal(posted,0);assert.deepEqual(errors,[]);checks.push('no API POSTs or JavaScript errors in static mode');
  await page.setViewportSize({width:390,height:844});await page.locator('[data-tab="converter"]').click();await openTool(page,'images');await page.screenshot({path:path.join(output,'mobile-converter.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);checks.push('static mobile workflow without overflow');
  const python=process.env.MODUPDF_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  const verified=spawnSync(python,[path.join(root,'tests/verify_static_outputs.py'),output],{encoding:'utf8'});assert.equal(verified.status,0,verified.stdout+verified.stderr);checks.push(verified.stdout.trim());
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:checks,errors},null,2));console.log(JSON.stringify({passed:checks.length,checks},null,2));
} finally {await browser.close();}
