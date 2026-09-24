const fs=require('fs');
const path=require('path');
const assert=require('node:assert/strict');
const {spawnSync}=require('child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..');
const python=process.env.MODUPDF_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const generated=spawnSync(python,[path.join(__dirname,'generate_fixtures.py')],{encoding:'utf8'});
assert.equal(generated.status,0,generated.stderr);
const fixtures=path.join(root,'artifacts/fixtures'),output=path.join(root,'artifacts/ui');fs.mkdirSync(output,{recursive:true});
const base=process.env.MODUPDF_URL||'http://127.0.0.1:8768';
const completed=[];
async function openTool(page,id) {const card=page.locator('#tool-'+id);if(!await card.evaluate(el=>el.open))await card.locator('summary').click();await card.locator('form').waitFor({state:'visible'});}
async function captureDownload(page,action,name) {
  const waiting=page.waitForEvent('download',{timeout:60000});waiting.catch(()=>{});
  let rejectFailure;const failure=new Promise((resolve,reject)=>{rejectFailure=reject;});
  const diagnose=async response=>{if(response.request().method()==='POST'&&response.url().includes('/api/')&&response.status()>=400){
    let detail='Falha de processamento';try{const payload=await response.json();if(typeof payload.detail==='string')detail=payload.detail;}catch{}
    rejectFailure(new Error(`${name}: API ${response.status()} ${detail}`));}};
  page.on('response',diagnose);
  try {await action();const download=await Promise.race([waiting,failure]);assert.equal(await download.failure(),null);const target=path.join(output,name||download.suggestedFilename());await download.saveAs(target);assert.ok(fs.statSync(target).size>0);return target;}
  finally {page.off('response',diagnose);}
}
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
  try {
    const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});const page=await context.newPage();const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base);await page.locator('#connectionStatus.online').waitFor({timeout:30000});await page.locator('#splash').waitFor({state:'detached'});
    for(const tab of ['organizar','otimizar','converter','editar','seguranca']) {
      await page.locator(`[data-tab="${tab}"]`).click();await page.locator(`#${tab}:visible`).waitFor();
      assert.equal(await page.locator('.panel:visible').count(),1);assert.equal(await page.locator(`[data-tab="${tab}"]`).getAttribute('aria-selected'),'true');
      await page.screenshot({path:path.join(output,`desktop-${tab}.png`),fullPage:true});
    }
    completed.push('five desktop tabs');
    await page.locator('[data-tab="organizar"]').focus();await page.keyboard.press('ArrowRight');assert.equal(await page.locator('.panel:visible').getAttribute('id'),'otimizar');
    await page.keyboard.press('End');assert.equal(await page.locator('.panel:visible').getAttribute('id'),'seguranca');
    await page.keyboard.press('Home');assert.equal(await page.locator('.panel:visible').getAttribute('id'),'organizar');completed.push('keyboard tab navigation with arrows, Home and End');
    const choosing=page.waitForEvent('filechooser');await page.locator('#addOrg').focus();await page.keyboard.press('Enter');
    const chooser=await choosing;await chooser.setFiles([path.join(fixtures,'a.pdf'),path.join(fixtures,'b.pdf')]);await page.waitForFunction(()=>document.querySelectorAll('.page').length===5);
    assert.equal(await page.locator('#orgFile').isVisible(),false);completed.push('single organizer upload button opens file chooser with keyboard');
    await page.waitForFunction(()=>[...document.querySelectorAll('.page canvas')].every(canvas=>canvas.width>0));
    const pixels=await page.locator('.page canvas').first().evaluate(canvas=>{const data=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;let dark=0;for(let i=0;i<data.length;i+=4)if(data[i]+data[i+1]+data[i+2]<600)dark++;return dark;});assert.ok(pixels>30,'thumbnail must show page contents');
    await page.locator('.page').first().click();await page.locator('[data-org="duplicate"]').click();assert.equal(await page.locator('.page').count(),6);
    await page.locator('[data-org="undo"]').click();assert.equal(await page.locator('.page').count(),5);await page.locator('[data-org="redo"]').click();assert.equal(await page.locator('.page').count(),6);
    await page.locator('.page').first().click();await page.locator('[data-org="rotate"]').click();await page.locator('[data-org="down"]').click();
    await page.locator('[data-org="none"]').click();const moved=await page.locator('.page').first().getAttribute('data-id');
    await page.locator('.page').first().dragTo(page.locator('.page').last(),{targetPosition:{x:110,y:100}});
    assert.notEqual(await page.locator('.page').first().getAttribute('data-id'),moved,'drag and drop must reorder pages');
    await page.locator('[data-org="all"]').click();assert.equal(await page.locator('.page.selected').count(),6);await page.locator('[data-org="none"]').click();assert.equal(await page.locator('.page.selected').count(),0);
    await page.waitForFunction(()=>[...document.querySelectorAll('.page canvas')].every(canvas=>canvas.width>0));
    const organizedOrder=await page.locator('.page').evaluateAll(elements=>elements.map(element=>({source:element.querySelector('.page-source').textContent,page:Number(element.querySelector('.page-number').textContent.split('Página ')[1]),rotation:element.querySelector('canvas').width>element.querySelector('canvas').height?90:0})));
    fs.writeFileSync(path.join(output,'organized-order.json'),JSON.stringify(organizedOrder));
    const organized=await captureDownload(page,()=>page.locator('#saveOrg').click(),'organized.pdf');
    await page.screenshot({path:path.join(output,'desktop-organized.png'),fullPage:true});
    completed.push('multi PDF upload, nonblank thumbnails, duplicate, rotate, move, undo, redo, selection, real drag/drop and save');
    await page.locator('#orgFile').setInputFiles(path.join(fixtures,'invalid.pdf'));await page.locator('#orgStatus.error').waitFor();assert.equal(await page.locator('.page').count(),6);
    completed.push('invalid upload preserves organizer state');
    for(const [tab,id,files,fields,name] of [
      ['organizar','merge',['a.pdf','b.pdf'],{},'merge.pdf'],['organizar','split',['a.pdf'],{pages:'3,1'},'split.pdf'],
      ['organizar','remove',['a.pdf'],{pages:'2'},'remove.pdf'],['organizar','rotate',['a.pdf'],{},'rotate.pdf'],
      ['otimizar','compress',['a.pdf'],{target_mb:'0.01'},'compressed.pdf'],['otimizar','repair',['a.pdf'],{},'repair.pdf'],
      ['otimizar','scan',['image.png'],{},'scan.pdf'],['converter','images',['image.png'],{},'images.pdf'],
      ['converter','pimg',['a.pdf'],{},'images.zip'],['converter','html',['example.html'],{},'html.pdf'],
      ['converter','docx',['a.pdf'],{},'word.docx'],['converter','xlsx',['table.pdf'],{},'tables.xlsx'],['converter','pptx',['a.pdf'],{},'slides.pptx'],
      ['editar','nums',['a.pdf'],{start:'7'},'numbered.pdf'],['editar','watermark',['a.pdf'],{text:'CONFIDENTIAL'},'watermark.pdf'],
      ['editar','crop',['a.pdf'],{margin:'20'},'cropped.pdf'],['seguranca','protect',['a.pdf'],{password:'secret'},'protected.pdf'],
      ['seguranca','compare',['a.pdf'],{},'comparison.pdf']]) {
      await page.locator(`[data-tab="${tab}"]`).click();await openTool(page,id);await page.locator(`#${id}-file`).setInputFiles(files.map(file=>path.join(fixtures,file)));
      for(const [field,value] of Object.entries(fields))await page.locator(`#${id}-${field}`).fill(value);
      if(id==='compare')await page.locator('#compare-file2').setInputFiles(path.join(fixtures,'b.pdf'));
      await captureDownload(page,()=>page.locator(`[data-run="${id}"]`).click(),name);completed.push(id+' upload/process/download');
    }
    await openTool(page,'unlock');await page.locator('#unlock-file').setInputFiles(path.join(output,'protected.pdf'));await page.locator('#unlock-password').fill('secret');await captureDownload(page,()=>page.locator('[data-run="unlock"]').click(),'unlocked.pdf');
    await openTool(page,'sign');await page.locator('#sign-file').setInputFiles(path.join(fixtures,'a.pdf'));await page.locator('#sign-certificate').setInputFiles(path.join(fixtures,'test-only.p12'));await page.locator('#sign-password').fill('test-only');await captureDownload(page,()=>page.locator('[data-run="sign"]').click(),'signed.pdf');completed.push('P12 certificate signature UI');
    await page.locator('[data-tab="editar"]').click();await openTool(page,'edit');await page.locator('#edit-file').setInputFiles(path.join(fixtures,'a.pdf'));await page.locator('[data-run="edit"]').click();await page.locator('#visualDialog[open]').waitFor();await page.locator('#visualText').fill('UI ADDED TEXT');
    await page.waitForFunction(()=>document.getElementById('visualCanvas').width>200);
    let box=await page.locator('#visualSurface').boundingBox();await page.mouse.move(box.x+box.width*.1,box.y+box.height*.4);await page.mouse.down();await page.mouse.move(box.x+box.width*.8,box.y+box.height*.55,{steps:8});await page.mouse.up();assert.equal(await page.locator('.operation-row').count(),1);
    await captureDownload(page,()=>page.locator('#visualSave').click(),'edited.pdf');await page.locator('[data-close="visualDialog"]').click();completed.push('visual text selection and edit download');
    await openTool(page,'forms');await page.locator('#forms-file').setInputFiles(path.join(fixtures,'form.pdf'));await page.locator('[data-run="forms"]').click();await page.locator('#formsDialog[open]').waitFor();await page.locator('[data-field-name="Name"]').fill('Pedro UI');await captureDownload(page,()=>page.locator('#formsSave').click(),'filled.pdf');await page.locator('[data-close="formsDialog"]').click();
    completed.push('interactive form fill and download');
    await openTool(page,'newforms');await page.locator('#newforms-file').setInputFiles(path.join(fixtures,'a.pdf'));await page.locator('[data-run="newforms"]').click();await page.locator('#visualDialog[open]').waitFor();await page.locator('#visualText').fill('UIField');
    await page.waitForFunction(()=>document.getElementById('visualCanvas').width>200);box=await page.locator('#visualSurface').boundingBox();await page.mouse.move(box.x+box.width*.1,box.y+box.height*.4);await page.mouse.down();await page.mouse.move(box.x+box.width*.8,box.y+box.height*.48,{steps:8});await page.mouse.up();await captureDownload(page,()=>page.locator('#visualSave').click(),'created-form.pdf');await page.locator('[data-close="visualDialog"]').click();completed.push('visual creation of interactive form field');
    await page.locator('[data-tab="seguranca"]').click();await openTool(page,'redact');await page.locator('#redact-file').setInputFiles(path.join(fixtures,'a.pdf'));await page.locator('[data-run="redact"]').click();await page.locator('#visualDialog[open]').waitFor();await page.waitForFunction(()=>document.getElementById('visualCanvas').width>200);
    box=await page.locator('#visualSurface').boundingBox();await page.mouse.move(box.x+box.width*.02,box.y+box.height*.04);await page.mouse.down();await page.mouse.move(box.x+box.width*.95,box.y+box.height*.15,{steps:8});await page.mouse.up();await captureDownload(page,()=>page.locator('#visualSave').click(),'redacted.pdf');await page.locator('[data-close="visualDialog"]').click();completed.push('visual permanent redaction selection and download');
    for(const [width,height] of [[390,844],[320,740],[768,1024]]) {
      await page.setViewportSize({width,height});
      for(const tab of ['organizar','otimizar','converter','editar','seguranca']) {
        await page.locator(`[data-tab="${tab}"]`).click();assert.equal(await page.locator('.panel:visible').count(),1);
        const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);assert.equal(overflow,false,`${width}px ${tab} must not overflow`);
        await page.screenshot({path:path.join(output,`${width}-${tab}.png`),fullPage:true});
      }
    }
    await page.setViewportSize({width:390,height:844});await page.locator('[data-tab="editar"]').click();await openTool(page,'edit');await page.locator('[data-run="edit"]').click();await page.locator('#visualDialog[open]').waitFor();await page.waitForTimeout(300);await page.screenshot({path:path.join(output,'mobile-editor.png')});await page.locator('#visualNext').click();await page.locator('#visualPageInfo').filter({hasText:'2 / 3'}).waitFor();await page.locator('[data-close="visualDialog"]').click();completed.push('mobile editor and page navigation');
    completed.push('all tabs on 320px, 390px and 768px without document overflow');
    // Verify a GitHub Pages style prefix serves relative assets and still connects to the API.
    await page.route('**/ModuPDF/**',async route=>{const url=new URL(route.request().url());url.pathname=url.pathname.replace('/ModuPDF/','/');const response=await route.fetch({url:url.href});await route.fulfill({response});});
    await page.goto(base+'/ModuPDF/');await page.locator('#connectionStatus.online').waitFor();assert.ok(await page.locator('.card').count()>20);completed.push('GitHub Pages base path assets');
    assert.deepEqual(errors,[],'no browser runtime errors');
    const verify=spawnSync(python,[path.join(__dirname,'verify_ui_outputs.py'),output],{encoding:'utf8'});assert.equal(verify.status,0,verify.stdout+verify.stderr);completed.push(verify.stdout.trim());
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:completed,errors},null,2));console.log(JSON.stringify({passed:completed.length,checks:completed},null,2));
  }finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
