import * as pdfjsLib from './vendor/pdfjs/build/pdf.mjs';
import {LOCAL_TOOLS, runLocal} from './local.js';
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdfjs/build/pdf.worker.mjs', import.meta.url).href;
const $ = id => document.getElementById(id);
const icons = () => window.lucide?.createIcons();
const pdfOptions = {isEvalSupported:false, enableXfa:false, maxImageSize:25000000,
  cMapUrl:new URL('./vendor/pdfjs/cmaps/',import.meta.url).href,cMapPacked:true,
  standardFontDataUrl:new URL('./vendor/pdfjs/standard_fonts/',import.meta.url).href,
  wasmUrl:new URL('./vendor/pdfjs/wasm/',import.meta.url).href};
let savedApi=null;try{savedApi=localStorage.getItem('modupdf-api');}catch{}
let apiBase = savedApi ?? window.MODUPDF_CONFIG?.apiBase ?? '';
let capabilities = null, online = false, maxUploadMB = 100, maxPages = 500;
const api = endpoint => (apiBase ? apiBase.replace(/\/$/,'') : location.origin) + endpoint;
const byteSize = bytes => bytes < 1024 * 1024 ? `${Math.max(1, Math.ceil(bytes/1024))} KB` : `${(bytes/1024/1024).toFixed(2)} MB`;
const localReady = () => !!window.PDFLib && !!window.JSZip;
function status(element, text, kind='') {element.hidden=false;element.className='status '+kind;element.textContent=text;}
function field(label,id,type='text',extra={}) {return {label,id,type,...extra};}
const select = (label,id,options) => field(label,id,'select',{options});
const tools = [
  {id:'merge',panel:'organizar',title:'Juntar PDF',icon:'combine',endpoint:'merge',multi:true},
  {id:'split',panel:'organizar',title:'Dividir / extrair',icon:'scissors',endpoint:'split',fields:[field('Páginas','pages','text',{placeholder:'1,3,5-8',required:true}),select('Resultado','mode',[['extract','PDF com páginas selecionadas'],['individual','Um PDF por página (ZIP)']])]},
  {id:'remove',panel:'organizar',title:'Remover páginas',icon:'file-minus-2',endpoint:'remove-pages',fields:[field('Páginas a remover','pages','text',{placeholder:'2,4,7-9',required:true})]},
  {id:'rotate',panel:'organizar',title:'Girar PDF',icon:'rotate-cw',endpoint:'rotate',fields:[select('Rotação','degrees',[['90','90°'],['180','180°'],['270','270°']])]},
  {id:'compress',panel:'otimizar',title:'Comprimir PDF',icon:'minimize-2',endpoint:'compress',fields:[select('Perfil','level',[['balanced','Equilibrada'],['lossless','Sem perda de qualidade'],['maximum','Maior redução de imagens']]),field('Meta aproximada (MB)','target_mb','number',{min:.01,step:.01,placeholder:'10'})],note:'A meta depende do documento. Texto e vetores são preservados; imagens podem perder qualidade.'},
  {id:'repair',panel:'otimizar',title:'Reparar PDF',icon:'wrench',endpoint:'repair'},
  {id:'ocr',panel:'otimizar',title:'OCR',icon:'scan-text',endpoint:'ocr',requires:'ocr',fields:[select('Idioma','language',[['por','Português'],['eng','Inglês'],['spa','Espanhol'],['por+eng','Português + inglês']])]},
  {id:'scan',panel:'otimizar',title:'Digitalização para PDF',icon:'scan',endpoint:'scan-to-pdf',accept:'.jpg,.jpeg,.png,.tif,.tiff,.webp',multi:true,fields:[field('Aplicar OCR','run_ocr','checkbox'),select('Idioma OCR','language',[['por','Português'],['eng','Inglês'],['spa','Espanhol']])]},
  {id:'images',panel:'converter',title:'Imagens para PDF',icon:'images',endpoint:'images-to-pdf',accept:'.jpg,.jpeg,.png,.tif,.tiff,.webp',multi:true},
  {id:'pimg',panel:'converter',title:'PDF para JPG / PNG',icon:'image',endpoint:'pdf-to-images',fields:[select('Formato','fmt',[['png','PNG'],['jpg','JPG']]),select('Resolução','dpi',[['150','150 DPI'],['72','72 DPI'],['300','300 DPI']])]},
  {id:'word',panel:'converter',title:'Word para PDF',icon:'file-text',endpoint:'office-to-pdf',accept:'.doc,.docx',requires:'office'},
  {id:'excel',panel:'converter',title:'Excel para PDF',icon:'sheet',endpoint:'office-to-pdf',accept:'.xls,.xlsx',requires:'office'},
  {id:'ppt',panel:'converter',title:'PowerPoint para PDF',icon:'presentation',endpoint:'office-to-pdf',accept:'.ppt,.pptx',requires:'office'},
  {id:'html',panel:'converter',title:'HTML para PDF',icon:'file-code-2',endpoint:'html-to-pdf',accept:'.html,.htm',note:'HTML estático. Scripts, imagens e recursos externos não são incluídos.'},
  {id:'docx',panel:'converter',title:'PDF para Word',icon:'file-text',endpoint:'pdf-to-office',requires:'docx',values:{target:'docx'},note:'Documento editável. PDFs escaneados precisam de OCR; o layout pode exigir revisão.'},
  {id:'xlsx',panel:'converter',title:'PDF para Excel',icon:'sheet',endpoint:'pdf-to-office',requires:'xlsx',values:{target:'xlsx'},note:'Extrai tabelas detectadas em planilhas editáveis.'},
  {id:'pptx',panel:'converter',title:'PDF para PowerPoint',icon:'presentation',endpoint:'pdf-to-office',requires:'pptx',values:{target:'pptx'},note:'Cada página vira um slide em imagem; o conteúdo interno não é editável.'},
  {id:'pdfa',panel:'converter',title:'PDF para PDF/A',icon:'archive',endpoint:'pdf-a',requires:'pdfa'},
  {id:'nums',panel:'editar',title:'Inserir números',icon:'list-ordered',endpoint:'add-page-numbers',fields:[field('Número inicial','start','number',{value:1,min:0,max:100000,required:true})]},
  {id:'watermark',panel:'editar',title:"Marca d'água",icon:'stamp',endpoint:'watermark',fields:[field('Texto','text','text',{placeholder:'CONFIDENCIAL',required:true,maxLength:200})]},
  {id:'crop',panel:'editar',title:'Recortar PDF',icon:'crop',endpoint:'crop',fields:[field('Margem (pontos)','margin','number',{value:20,min:0,step:1,required:true})]},
  {id:'edit',panel:'editar',title:'Editar PDF',icon:'pencil',custom:'visual',mode:'edit'},
  {id:'forms',panel:'editar',title:'Preencher formulário',icon:'text-cursor-input',custom:'forms'},
  {id:'newforms',panel:'editar',title:'Criar campos de formulário',icon:'form-input',custom:'visual',mode:'fields'},
  {id:'protect',panel:'seguranca',title:'Proteger PDF',icon:'lock-keyhole',endpoint:'protect',fields:[field('Senha','password','password',{required:true,maxLength:256})]},
  {id:'unlock',panel:'seguranca',title:'Desbloquear PDF',icon:'lock-keyhole-open',endpoint:'unlock',fields:[field('Senha atual','password','password')]},
  {id:'sign',panel:'seguranca',title:'Assinatura digital',icon:'signature',endpoint:'sign',requires:'sign',fields:[field('Certificado P12 / PFX','certificate','file',{accept:'.p12,.pfx',required:true}),field('Senha do certificado','password','password'),field('Motivo (opcional)','reason')],note:'O certificado é usado apenas nesta operação. A confiança da assinatura depende do certificado.'},
  {id:'redact',panel:'seguranca',title:'Ocultar informações',icon:'rectangle-ellipsis',custom:'visual',mode:'redact',note:'Remove permanentemente as áreas selecionadas. Confira todas as páginas antes de compartilhar.'},
  {id:'compare',panel:'seguranca',title:'Comparar PDFs',icon:'columns-2',endpoint:'compare',fileKey:'file1',fields:[field('Segundo PDF','file2','file',{accept:'.pdf',required:true})],note:'Relatório de diferenças visuais entre páginas correspondentes.'}
];

function createControl(def, prefix) {
  const wrapper=document.createElement('div'),label=document.createElement('label');
  const id=prefix+'-'+def.id;label.htmlFor=id;label.textContent=def.label;
  const control=document.createElement(def.type==='select'?'select':'input');control.id=id;control.name=def.id;
  if(def.type==='select') for(const [value,text] of def.options) control.add(new Option(text,value));
  else control.type=def.type;
  for(const key of ['value','placeholder','min','max','step','required','accept','maxLength']) if(def[key]!==undefined) control[key]=def[key];
  if(def.type==='password') control.autocomplete='off';
  if(def.type==='checkbox') {label.className='checkbox-label';label.prepend(control);wrapper.append(label);}
  else wrapper.append(label,control);
  return wrapper;
}
function mountTools() {
  for(const tool of tools) {
    const card=document.createElement('details');card.className='card';card.id='tool-'+tool.id;
    const heading=document.createElement('summary');heading.className='card-heading';
    const icon=document.createElement('i');icon.dataset.lucide=tool.icon;
    const title=document.createElement('h3');title.textContent=tool.title;heading.append(icon,title);
    const state=document.createElement('span');state.className='tool-state';state.id=tool.id+'-state';state.hidden=true;title.append(state);
    const chevron=document.createElement('i');chevron.dataset.lucide='chevron-down';chevron.className='card-toggle';heading.append(chevron);
    const form=document.createElement('form');form.className='card-body';
    const main=createControl(field(tool.id==='compare'?'Primeiro PDF':'Arquivo'+(tool.multi?'s':''),'file','file',{accept:tool.accept||'.pdf',required:true}),tool.id);
    main.querySelector('input').multiple=!!tool.multi;form.append(main);
    for(const def of tool.fields||[]) form.append(createControl(def,tool.id));
    if(tool.note) {const note=document.createElement('p');note.className='note';note.textContent=tool.note;form.append(note);}
    const availability=document.createElement('p');availability.className='note';availability.id=tool.id+'-availability';availability.hidden=true;
    const button=document.createElement('button');button.type='submit';button.className='primary';button.dataset.run=tool.id;
    const actionIcon=document.createElement('i');actionIcon.dataset.lucide=tool.custom?'arrow-up-right':'arrow-right';button.append(actionIcon,document.createTextNode(tool.custom?'Abrir':'Processar'));
    const result=document.createElement('div');result.id=tool.id+'-result';result.className='status';result.setAttribute('role','status');result.hidden=true;
    form.append(availability,button,result);card.append(heading,form);
    document.querySelector(`[data-tools="${tool.panel}"]`).append(card);
    form.addEventListener('submit',event=>{event.preventDefault();runTool(tool,form,button,result);});
    card.addEventListener('toggle',()=>{if(card.open)for(const other of card.parentElement.querySelectorAll('details[open]'))if(other!==card)other.open=false;});
    if(tool.id==='compress') main.querySelector('input').addEventListener('change',event=>{const f=event.target.files[0];if(f)status(result,'Original: '+byteSize(f.size));});
  }
  for(const tab of document.querySelectorAll('[data-tab]')) {const count=document.createElement('span');count.className='tab-count';count.setAttribute('aria-hidden','true');count.textContent=tools.filter(tool=>tool.panel===tab.dataset.tab).length;tab.append(count);}
}
function switchTab(id, focus=false) {
  if(!document.querySelector(`[data-tab="${id}"]`)) id='organizar';
  for(const button of document.querySelectorAll('[data-tab]')) {
    const active=button.dataset.tab===id;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;
    if(active&&focus)button.focus();
  }
  for(const panel of document.querySelectorAll('.panel')) {const active=panel.id===id;panel.hidden=!active;panel.classList.toggle('active',active);}
  history.replaceState(null,'','#'+id);
}
window.switchTab=switchTab;window.tab=(id)=>switchTab(id);
function validateFiles(files) {
  if(!files.length) throw new Error('Selecione um arquivo.');
  if(files.reduce((total,file)=>total+file.size,0)>maxUploadMB*1024**2) throw new Error(`Limite total por operação: ${maxUploadMB} MB.`);
  if(files.some(file=>!file.size)) throw new Error('Um dos arquivos está vazio.');
}
async function loadPdf(file,data=null) {
  const task=pdfjsLib.getDocument({...pdfOptions,data:data??new Uint8Array(await file.arrayBuffer())});
  try{return await task.promise;}catch(error){await task.destroy();throw error;}
}
async function request(endpoint,body) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),360000);
  try {
    const response=await fetch(api('/api/'+endpoint),{method:'POST',body,signal:controller.signal});
    if(!response.ok) {
      let detail;try {detail=(await response.json()).detail;}catch{detail='O servidor não conseguiu processar o arquivo.';}
      if(Array.isArray(detail)) detail='Confira os campos obrigatórios e os valores informados.';
      throw new Error(detail||`Erro ${response.status}`);
    }
    return response;
  }catch(error) {
    if(error.name==='AbortError')throw new Error('O tempo de espera terminou. Tente um arquivo menor.');
    if(error instanceof TypeError)throw new Error('Não foi possível acessar o servidor. Verifique a conexão.');
    throw error;
  }finally {clearTimeout(timer);}
}
function filename(response) {
  const header=response.headers.get('content-disposition')||'';
  const match=header.match(/filename\*=(?:UTF-8'')?([^;]+)|filename="([^"]+)"|filename=([^;]+)/i);
  try{return match?decodeURIComponent((match[1]||match[2]||match[3]).trim()):'resultado.pdf';}catch{return 'resultado.pdf';}
}
async function download(blob,name,picker=false) {
  if(picker && window.showSaveFilePicker) {
    try {const handle=await window.showSaveFilePicker({suggestedName:name});const stream=await handle.createWritable();await stream.write(blob);await stream.close();return;}
    catch(error) {if(error.name==='AbortError')return;}
  }
  const url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download=name;document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
}
async function presentResult(response,element) {
  const blob=await response.blob(),name=filename(response);
  let message=`Concluído: ${name} (${byteSize(blob.size)}).`;
  if(response.headers.has('x-original-bytes')) {
    const target=response.headers.get('x-target-met');
    message=`Original: ${byteSize(Number(response.headers.get('x-original-bytes')))}\nFinal: ${byteSize(Number(response.headers.get('x-final-bytes')))}\nRedução: ${response.headers.get('x-reduction-percent')}%`;
    if(target!=='not-set')message+='\n'+(target==='true'?'Meta atingida.':'Meta não atingida com os limites de qualidade deste perfil.');
  }
  if(response.headers.get('x-pdfa-validation')==='not-independent')message+='\nPDF/A gerado pelo motor de conversão; validação independente indisponível neste servidor.';
  status(element,message);
  const button=document.createElement('button');button.type='button';button.className='result-download';button.innerHTML='<i data-lucide="download"></i>';button.append(document.createTextNode('Baixar resultado'));
  button.addEventListener('click',()=>download(blob,name,true));element.append(button);icons();
  await download(blob,name);
}
async function runTool(tool,form,button,result) {
  button.disabled=true;button.dataset.busy='true';
  try {
    const files=[...$(tool.id+'-file').files];
    const extraFiles=(tool.fields||[]).filter(f=>f.type==='file').flatMap(f=>[...$(tool.id+'-'+f.id).files]);validateFiles([...files,...extraFiles]);
    if(tool.custom==='visual')return await openVisual(files[0],tool.mode);
    if(tool.custom==='forms')return await openForms(files[0]);
    if(!online&&LOCAL_TOOLS.has(tool.id)&&localReady()) {
      const values=Object.fromEntries(new FormData(form));
      status(result,'Processando localmente…','busy');
      return await presentResult(await runLocal(tool.id,files,values,{maxPages,loadPdf}),result);
    }
    const body=new FormData();for(const file of files)body.append(tool.multi?'files':tool.fileKey||'file',file);
    for(const def of tool.fields||[]) {
      const control=$(tool.id+'-'+def.id);
      if(def.type==='file') {if(control.files[0])body.append(def.id,control.files[0]);}
      else if(def.type==='checkbox')body.append(def.id,String(control.checked));
      else if(control.value!=='')body.append(def.id,control.value);
    }
    for(const [key,value] of Object.entries(tool.values||{}))body.append(key,value);
    status(result,'Processando…','busy');await presentResult(await request(tool.endpoint,body),result);
  }catch(error) {status(result,error.message,'error');}
  finally {delete button.dataset.busy;refreshAvailability();}
}
function refreshAvailability() {
  for(const tool of tools) {
    const button=document.querySelector(`[data-run="${tool.id}"]`),note=$(tool.id+'-availability');
    const local=!online&&localReady()&&LOCAL_TOOLS.has(tool.id);
    const dependency=tool.requires&&!capabilities?.tools?.[tool.requires];
    const requiresServer=!tool.custom || tool.custom==='forms';
    button.disabled=!!button.dataset.busy||(requiresServer&&!online&&!local)||!!dependency;
    $('tool-'+tool.id).dataset.unavailable=String(button.disabled&&!button.dataset.busy);
    const state=$(tool.id+'-state');state.hidden=!(dependency||(!online&&requiresServer&&!local));state.textContent=!online?'Servidor necessário':'Motor ausente';
    note.hidden=!(dependency||(!online&&requiresServer&&!local));
    note.textContent=!online?'Conecte um servidor para usar esta operação.':dependency?'Indisponível neste servidor: motor de '+({office:'Office',ocr:'OCR',pdfa:'PDF/A',sign:'assinatura digital',docx:'Word',xlsx:'Excel',pptx:'PowerPoint'}[tool.requires])+' ausente.':'';
  }
  for(const id of ['images','scan'])$(id+'-file').accept=online?'.jpg,.jpeg,.png,.tif,.tiff,.webp':'.jpg,.jpeg,.png';
  const profile=$('compress-level');for(const option of profile.options)option.disabled=!online&&option.value!=='lossless';if(!online)profile.value='lossless';
  $('scan-run_ocr').disabled=!capabilities?.tools?.ocr;if($('scan-run_ocr').disabled)$('scan-run_ocr').checked=false;
  updateOrgControls();
}
async function connect() {
  try {
    const response=await fetch(api('/api/system/capabilities'),{signal:AbortSignal.timeout(10000)});
    if(!response.ok)throw new Error();capabilities=await response.json();if(!capabilities.tools)throw new Error();
    online=true;maxUploadMB=capabilities.max_upload_mb;maxPages=capabilities.max_pages;
    $('connectionStatus').textContent='Servidor conectado';$('connectionStatus').className='online';$('uploadLimit').textContent=`Limite por operação: ${maxUploadMB} MB`;
  }catch {online=false;capabilities=null;$('connectionStatus').textContent=localReady()?'Modo local':'Servidor desconectado';$('connectionStatus').className=localReady()?'local':'offline';}
  refreshAvailability();return online;
}

let sources=[],items=[],selected=new Set(),past=[{sources:[],items:[]}],future=[],renderVersion=0,loadingOrg=false;
const sourcePool=new Set();
const snapshot=()=>({sources:[...sources],items:items.map(item=>({...item}))});
function commit() {
  past.push(snapshot());if(past.length>51)past.shift();future=[];renderOrganizer();
  const retained=new Set([...sources,...past.flatMap(state=>state.sources),...future.flatMap(state=>state.sources)]);
  for(const source of sourcePool)if(!retained.has(source)){source.pdf.loadingTask.destroy().catch(()=>{});sourcePool.delete(source);}
}
function restore(state) {sources=[...state.sources];items=state.items.map(item=>({...item}));selected.clear();renderOrganizer();}
function undoOrg() {if(past.length<2)return;future.push(past.pop());restore(past.at(-1));}
function redoOrg() {if(!future.length)return;const state=future.pop();past.push(state);restore(state);}
function updateOrgControls() {
  $('addOrg').disabled=loadingOrg;
  for(const name of ['up','down','rotate','duplicate','delete'])document.querySelector(`[data-org="${name}"]`).disabled=!selected.size||loadingOrg;
  document.querySelector('[data-org="undo"]').disabled=past.length<2||loadingOrg;
  document.querySelector('[data-org="redo"]').disabled=!future.length||loadingOrg;
  $('saveOrg').disabled=(!online&&!localReady())||!items.length||loadingOrg||!!$('saveOrg').dataset.busy;
  $('selectedCount').textContent=selected.size+' selecionadas';$('orgCount').textContent=items.length+' páginas';$('historyInfo').textContent=`Histórico: ${past.length-1} alterações`;
}
function syncSelection() {document.querySelectorAll('.page').forEach(el=>{const active=selected.has(el.dataset.id);el.classList.toggle('selected',active);el.setAttribute('aria-pressed',String(active));el.querySelector('input').checked=active;});updateOrgControls();}
async function addPdfFiles(files) {
  if(loadingOrg)return;loadingOrg=true;updateOrgControls();
  try {
    const incoming=[...files];validateFiles([...sources.map(source=>source.file),...incoming]);
    let added=0;
    for(const file of incoming) {
      if(sources.some(source=>source.file.name===file.name&&source.file.size===file.size&&source.file.lastModified===file.lastModified))continue;
      if(!file.name.toLowerCase().endsWith('.pdf'))throw new Error('Selecione somente arquivos PDF.');
      const data=new Uint8Array(await file.arrayBuffer());if(!new TextDecoder().decode(data.subarray(0,1024)).includes('%PDF-'))throw new Error(`PDF inválido: ${file.name}`);
      status($('orgStatus'),'Carregando '+file.name+'…','busy');
      const document=await loadPdf(file,data);
      if(items.length+document.numPages>maxPages){await document.loadingTask.destroy();throw new Error(`O organizador aceita até ${maxPages} páginas.`);}
      const source={id:crypto.randomUUID(),file,pdf:document};sources.push(source);sourcePool.add(source);
      for(let page=1;page<=document.numPages;page++)items.push({id:crypto.randomUUID(),sourceId:source.id,page,rotation:0});
      added++;
    }
    if(added)commit();status($('orgStatus'),`${sources.length} PDF(s), ${items.length} página(s).`);
  }catch(error) {if(JSON.stringify(items)!==JSON.stringify(past.at(-1).items))commit();status($('orgStatus'),error.name==='PasswordException'?'PDF protegido. Desbloqueie-o antes de organizar.':error.message,'error');}
  finally {loadingOrg=false;$('orgFile').value='';updateOrgControls();}
}
async function renderOrganizer() {
  const version=++renderVersion;
  selected=new Set([...selected].filter(id=>items.some(item=>item.id===id)));
  $('pdfList').replaceChildren();
  for(const source of sources) {
    const row=document.createElement('div');row.className='pdf-item';
    const name=document.createElement('div');name.className='pdf-name';name.textContent=source.file.name;name.title=source.file.name;
    const count=document.createElement('span');count.className='pdf-count';count.textContent=items.filter(item=>item.sourceId===source.id).length+' páginas';name.append(count);
    const remove=document.createElement('button');remove.type='button';remove.className='icon danger';remove.title='Remover PDF';remove.setAttribute('aria-label','Remover '+source.file.name);remove.innerHTML='<i data-lucide="x"></i>';
    remove.onclick=()=>{sources=sources.filter(s=>s.id!==source.id);items=items.filter(i=>i.sourceId!==source.id);commit();};row.append(name,remove);$('pdfList').append(row);
  }
  $('pages').replaceChildren();
  if(!items.length)$('pages').innerHTML='<div class="empty"><i data-lucide="files"></i><span>Nenhum PDF selecionado</span></div>';
  const renders=[];
  for(const [index,item] of items.entries()) {
    const source=sources.find(s=>s.id===item.sourceId),element=document.createElement('div');element.className='page';element.dataset.id=item.id;element.draggable=true;element.tabIndex=0;element.setAttribute('role','button');element.setAttribute('aria-label',`Posição ${index+1}, página ${item.page}, ${source.file.name}`);
    const thumbnail=document.createElement('div');thumbnail.className='thumbnail';const canvas=document.createElement('canvas');canvas.width=0;canvas.height=0;thumbnail.append(canvas);
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.className='page-check';checkbox.tabIndex=-1;checkbox.setAttribute('aria-label',`Selecionar página ${item.page}`);
    const number=document.createElement('div');number.className='page-number';number.textContent=`${index+1} · Página ${item.page}`;
    const filename=document.createElement('div');filename.className='page-source';filename.textContent=source.file.name;element.append(thumbnail,checkbox,number,filename);
    const toggle=()=>{selected.has(item.id)?selected.delete(item.id):selected.add(item.id);syncSelection();};element.onclick=toggle;element.onkeydown=event=>{if(event.key===' '||event.key==='Enter'){event.preventDefault();toggle();}};
    element.ondragstart=event=>{if(!selected.has(item.id)){selected.clear();selected.add(item.id);syncSelection();}element.classList.add('dragging');event.dataTransfer.setData('application/x-modupdf-page',item.id);event.dataTransfer.effectAllowed='move';};
    element.ondragend=()=>{document.querySelectorAll('.page').forEach(el=>el.classList.remove('dragging','insert-before','insert-after'));};
    element.ondragover=event=>{if(!event.dataTransfer.types.includes('application/x-modupdf-page'))return;event.preventDefault();const after=event.clientX>element.getBoundingClientRect().left+element.offsetWidth/2;element.classList.toggle('insert-before',!after);element.classList.toggle('insert-after',after);};
    element.ondragleave=()=>element.classList.remove('insert-before','insert-after');
    element.ondrop=event=>{if(!event.dataTransfer.types.includes('application/x-modupdf-page'))return;event.preventDefault();event.stopPropagation();element.classList.remove('insert-before','insert-after');if(selected.has(item.id))return;const moving=items.filter(i=>selected.has(i.id));const rest=items.filter(i=>!selected.has(i.id));const after=event.clientX>element.getBoundingClientRect().left+element.offsetWidth/2;const at=rest.findIndex(i=>i.id===item.id)+(after?1:0);rest.splice(at,0,...moving);items=rest;commit();};
    $('pages').append(element);
    renders.push({source,item,canvas});
  }
  icons();syncSelection();
  for(const {source,item,canvas} of renders) {
    if(version!==renderVersion)return;
    try {const page=await source.pdf.getPage(item.page);const viewport=page.getViewport({scale:.3,rotation:(page.rotate+item.rotation)%360});canvas.width=viewport.width;canvas.height=viewport.height;await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;}
    catch {if(version===renderVersion)status($('orgStatus'),'Uma miniatura não pôde ser carregada.','error');}
  }
}
function mutateOrg(action) {
  if(action==='all'){items.forEach(i=>selected.add(i.id));return syncSelection();}
  if(action==='none'){selected.clear();return syncSelection();}
  if(action==='undo')return undoOrg();if(action==='redo')return redoOrg();
  if(action==='clear'){if(!items.length&&!sources.length)return;sources=[];items=[];selected.clear();commit();return;}
  if(!selected.size)return;
  if(action==='rotate')items=items.map(item=>selected.has(item.id)?{...item,rotation:(item.rotation+90)%360}:item);
  if(action==='delete')items=items.filter(item=>!selected.has(item.id));
  if(action==='duplicate') {if(items.length+selected.size>maxPages)return status($('orgStatus'),`Limite de ${maxPages} páginas.`,'error');items=items.flatMap(item=>selected.has(item.id)?[item,{...item,id:crypto.randomUUID()}]:[item]);}
  if(action==='up')for(let index=1;index<items.length;index++)if(selected.has(items[index].id)&&!selected.has(items[index-1].id))[items[index-1],items[index]]=[items[index],items[index-1]];
  if(action==='down')for(let index=items.length-2;index>=0;index--)if(selected.has(items[index].id)&&!selected.has(items[index+1].id))[items[index],items[index+1]]=[items[index+1],items[index]];
  commit();
}
async function saveOrg() {
  $('saveOrg').dataset.busy='true';updateOrgControls();
  try {
    const files=sources.map(source=>source.file);validateFiles(files);
    const order=items.map(item=>({fileIndex:sources.findIndex(s=>s.id===item.sourceId),page:item.page,rotation:item.rotation}));
    if(!online&&localReady()) {status($('orgStatus'),'Gerando PDF localmente…','busy');return await presentResult(await runLocal('organize',files,{}, {maxPages,loadPdf,order}),$('orgStatus'));}
    const body=new FormData();files.forEach(file=>body.append('files',file));body.append('order',JSON.stringify(order));
    status($('orgStatus'),'Gerando PDF…','busy');await presentResult(await request('organize-multi',body),$('orgStatus'));
  }catch(error){status($('orgStatus'),error.message,'error');}
  finally {delete $('saveOrg').dataset.busy;updateOrgControls();}
}

let visual=null,visualRender=0,visualTask=null,selectionStart=null;
async function openVisual(file,mode) {
  const pdf=await loadPdf(file);
  if(pdf.numPages>maxPages){await pdf.loadingTask.destroy();throw new Error(`Limite de ${maxPages} páginas.`);}
  visual={file,pdf,mode,page:1,operations:[],fields:[]};
  $('visualTitle').textContent={edit:'Editar PDF',redact:'Ocultar informações',fields:'Criar campos de formulário'}[mode];
  $('visualMode').disabled=mode!=='edit';$('visualMode').value='text';
  $('visualMode').hidden=mode!=='edit';$('visualMode').previousElementSibling.hidden=mode!=='edit';
  $('visualText').value='';$('visualImage').value='';$('visualStatus').hidden=true;$('visualSave').disabled=!online;
  $('visualText').previousElementSibling.textContent=mode==='fields'?'Nome do campo':'Texto';
  $('visualText').hidden=mode==='redact';$('visualText').previousElementSibling.hidden=mode==='redact';
  $('visualTypography').hidden=mode!=='edit';$('visualImage').hidden=mode!=='edit';$('visualImage').previousElementSibling.hidden=mode!=='edit';
  $('visualDialog').showModal();await renderVisual();renderOperationList();
}
async function renderVisual() {
  if(!visual)return;const version=++visualRender;
  if(visualTask){visualTask.cancel();try{await visualTask.promise;}catch{}visualTask=null;}
  const page=await visual.pdf.getPage(visual.page);if(version!==visualRender)return;
  const width=Math.max(260,Math.min(760,$('visualSurface').parentElement.clientWidth));const original=page.getViewport({scale:1});
  const viewport=page.getViewport({scale:width/original.width});
  const canvas=$('visualCanvas');canvas.width=viewport.width;canvas.height=viewport.height;
  visualTask=page.render({canvasContext:canvas.getContext('2d'),viewport});
  try{await visualTask.promise;}catch(error){if(error.name!=='RenderingCancelledException')throw error;}
  if(version!==visualRender)return;
  $('visualPageInfo').textContent=visual.page+' / '+visual.pdf.numPages;
  $('visualPrev').disabled=visual.page===1;$('visualNext').disabled=visual.page===visual.pdf.numPages;renderVisualOverlay();
}
function renderVisualOverlay(draft=null) {
  $('visualOverlay').replaceChildren();if(!visual)return;
  for(const item of [...visual.operations,...visual.fields,...(draft?[draft]:[])].filter(item=>item.page===visual.page)) {
    const box=document.createElement('div');box.className='selection-box '+(item.type||'field');
    Object.assign(box.style,{left:item.x*100+'%',top:item.y*100+'%',width:item.w*100+'%',height:item.h*100+'%'});
    box.textContent=item.type==='text'?item.text:item.name||'';
    if(item.type==='image'){const img=document.createElement('img');img.src=item.image;img.style.cssText='width:100%;height:100%;object-fit:contain';box.append(img);}
    $('visualOverlay').append(box);
  }
}
function renderOperationList() {
  $('visualOperations').replaceChildren();if(!visual)return;
  const list=visual.mode==='fields'?visual.fields:visual.operations;
  list.forEach((item,index)=>{const row=document.createElement('div');row.className='operation-row';const text=document.createElement('span');text.textContent=`P${item.page} · ${item.name||({text:'Texto',rectangle:'Retângulo',image:'Imagem',redact:'Ocultação'}[item.type])}`;
    const button=document.createElement('button');button.type='button';button.className='icon danger';button.setAttribute('aria-label','Excluir seleção '+(index+1));button.innerHTML='<i data-lucide="x"></i>';button.onclick=()=>{list.splice(index,1);renderOperationList();renderVisualOverlay();};row.append(text,button);$('visualOperations').append(row);});icons();
}
const pointerPosition=event=>{const rect=$('visualSurface').getBoundingClientRect();return {x:Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),y:Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))};};
const pointerRect=end=>({page:visual.page,x:Math.min(selectionStart.x,end.x),y:Math.min(selectionStart.y,end.y),w:Math.abs(selectionStart.x-end.x),h:Math.abs(selectionStart.y-end.y)});
async function finishSelection(event) {
  if(!selectionStart||!visual)return;const rect=pointerRect(pointerPosition(event));selectionStart=null;
  if(rect.w<.01||rect.h<.01){renderVisualOverlay();return;}
  try {
    if(visual.mode==='fields') {
      const name=$('visualText').value.trim();if(!name)throw new Error('Informe o nome do campo.');if(visual.fields.some(field=>field.name===name))throw new Error('O nome do campo já foi usado.');visual.fields.push({...rect,name});
    }else {
      const type=visual.mode==='redact'?'redact':$('visualMode').value;
      const operation={...rect,type,text:$('visualText').value,color:$('visualColor').value,size:Number($('visualSize').value)};
      if(type==='text'&&!operation.text.trim())throw new Error('Informe o texto antes de selecionar a área.');
      if(type==='image') {const file=$('visualImage').files[0];if(!file)throw new Error('Selecione uma imagem.');if(file.size>5*1024**2)throw new Error('A imagem deve ter até 5 MB.');operation.image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});}
      visual.operations.push(operation);
    }
    $('visualStatus').hidden=true;renderOperationList();
  }catch(error){status($('visualStatus'),error.message,'error');}
  renderVisualOverlay();
}
async function saveVisual() {
  $('visualSave').disabled=true;
  try {const body=new FormData();body.append('file',visual.file);
    const list=visual.mode==='fields'?visual.fields:visual.operations;if(!list.length)throw new Error('Adicione pelo menos uma seleção.');
    if(visual.mode==='fields')body.append('fields',JSON.stringify(list));else body.append('operations',JSON.stringify(list));
    status($('visualStatus'),'Processando…','busy');await presentResult(await request(visual.mode==='fields'?'forms':visual.mode==='redact'?'redact':'edit',body),$('visualStatus'));
  }catch(error){status($('visualStatus'),error.message,'error');}finally{$('visualSave').disabled=!online;}
}
let formFile=null;
async function openForms(file) {
  const body=new FormData();body.append('file',file);const data=await (await request('forms/inspect',body)).json();formFile=file;$('formFields').replaceChildren();$('formsStatus').hidden=true;
  const seen=new Set();let editable=0;
  for(const def of data.fields) {
    if(seen.has(def.name))continue;seen.add(def.name);
    const supported=['Text','CheckBox','ComboBox','ListBox'].includes(def.type);if(!def.readonly&&supported)editable++;
    const fieldDef=def.type==='CheckBox'?field(def.name,def.name,'checkbox'):def.options.length?select(def.name,def.name,def.options.map(option=>[option,option])):field(def.name,def.name);
    const element=createControl(fieldDef,'form'),control=element.querySelector('input,select');control.dataset.fieldName=def.name;
    if(def.type==='CheckBox')control.checked=def.value!==''&&def.value!=='Off';else control.value=def.value;control.disabled=def.readonly||!supported;
    $('formFields').append(element);
  }
  if(!data.fields.length)status($('formsStatus'),'Este PDF não tem campos preenchíveis. Use “Criar campos de formulário” para adicionar campos.');
  $('formsSave').disabled=!editable;$('formsDialog').showModal();
}
async function saveForms() {
  $('formsSave').disabled=true;
  try {const values={};for(const control of $('formFields').querySelectorAll('[data-field-name]'))if(!control.disabled)values[control.dataset.fieldName]=control.type==='checkbox'?control.checked:control.value;
    const body=new FormData();body.append('file',formFile);body.append('values',JSON.stringify(values));status($('formsStatus'),'Salvando…','busy');await presentResult(await request('forms',body),$('formsStatus'));
  }catch(error){status($('formsStatus'),error.message,'error');}finally{$('formsSave').disabled=!online;}
}

mountTools();icons();
const compactNavigation=matchMedia('(max-width:850px)');
const orientNavigation=()=>document.querySelector('.tabs').setAttribute('aria-orientation',compactNavigation.matches?'horizontal':'vertical');orientNavigation();compactNavigation.addEventListener('change',orientNavigation);
document.querySelectorAll('[data-tab]').forEach(button=>{button.addEventListener('click',()=>switchTab(button.dataset.tab));button.addEventListener('keydown',event=>{const buttons=[...document.querySelectorAll('[data-tab]')];let index=buttons.indexOf(button);if(event.key==='ArrowRight'||(!compactNavigation.matches&&event.key==='ArrowDown'))index=(index+1)%buttons.length;else if(event.key==='ArrowLeft'||(!compactNavigation.matches&&event.key==='ArrowUp'))index=(index+buttons.length-1)%buttons.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=buttons.length-1;else return;event.preventDefault();switchTab(buttons[index].dataset.tab,true);});});
window.addEventListener('hashchange',()=>switchTab(location.hash.slice(1)));switchTab(location.hash.slice(1));
document.querySelectorAll('img').forEach(image=>{image.addEventListener('error',()=>image.hidden=true);if(image.complete&&!image.naturalWidth)image.hidden=true;});
document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>$(button.dataset.close).close());
$('connectionButton').onclick=()=>{$('apiBase').value=apiBase;$('connectionMessage').hidden=true;$('connectionDialog').showModal();};
$('connectionForm').onsubmit=async event=>{event.preventDefault();const value=$('apiBase').value.trim();
  if(value){const url=new URL(value);if(url.protocol!=='https:'&&!['localhost','127.0.0.1','[::1]'].includes(url.hostname))return status($('connectionMessage'),'Use HTTPS para conectar a um servidor público.','error');apiBase=url.origin;}else apiBase='';
  try{localStorage.setItem('modupdf-api',apiBase);}catch{}const ok=await connect();status($('connectionMessage'),ok?'Conectado.':'Servidor indisponível ou conexão bloqueada por CORS.',ok?'':'error');if(ok)$('connectionDialog').close();};
$('addOrg').onclick=()=>$('orgFile').click();
$('orgFile').addEventListener('change',event=>addPdfFiles(event.target.files));
document.querySelectorAll('[data-org]').forEach(button=>button.onclick=()=>mutateOrg(button.dataset.org));$('saveOrg').onclick=saveOrg;
$('organizer').addEventListener('dragover',event=>{if(event.dataTransfer.types.includes('Files'))event.preventDefault();});
$('organizer').addEventListener('drop',event=>{if(!event.dataTransfer.types.includes('Files'))return;event.preventDefault();addPdfFiles(event.dataTransfer.files);});
$('visualPrev').onclick=async()=>{if(visual.page>1){visual.page--;await renderVisual();}};$('visualNext').onclick=async()=>{if(visual.page<visual.pdf.numPages){visual.page++;await renderVisual();}};
$('visualSurface').addEventListener('pointerdown',event=>{if(!visual||event.button!==0)return;selectionStart=pointerPosition(event);$('visualSurface').setPointerCapture(event.pointerId);event.preventDefault();});
$('visualSurface').addEventListener('pointermove',event=>{if(selectionStart)renderVisualOverlay({...pointerRect(pointerPosition(event)),type:visual.mode==='redact'?'redact':'rectangle'});});
$('visualSurface').addEventListener('pointerup',finishSelection);$('visualSurface').addEventListener('pointercancel',()=>{selectionStart=null;renderVisualOverlay();});
$('visualDialog').addEventListener('close',()=>{selectionStart=null;visualRender++;visualTask?.cancel();visualTask=null;visual?.pdf.loadingTask.destroy().catch(()=>{});visual=null;});$('visualSave').onclick=saveVisual;$('formsSave').onclick=saveForms;
window.addEventListener('resize',()=>{if(visual&&!$('visualDialog').hidden)renderVisual();});
$('splash').classList.add('out');setTimeout(()=>$('splash').remove(),250);
connect();
