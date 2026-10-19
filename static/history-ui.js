export function createHistoryUI({api, esc, badge, option, openModal, getState, getCurrent, refresh, toast, sourceModal, formatVisibleText}) {
  let upload=null, selectedFile=null, results=[];
  const kinds=['Historical ticket','Resolution guide','Investigation report','Known issue','Change record'];
  const qualities=['Unreviewed','Reviewed','Verified fix','Workaround','Unresolved findings'];
  const input=(key,label,value='',required=false)=>`<label>${esc(label)}<input name="${key}" value="${esc(value)}" ${required?'required':''} maxlength="${key==='source_reference'?1000:200}"></label>`;
  const select=(key,label,values,chosen)=>`<label>${esc(label)}<select name="${key}">${values.map(v=>`<option value="${esc(v)}" ${v===chosen?'selected':''}>${esc(displayTitle(v))}</option>`).join('')}</select></label>`;
  const isDemo=s=>s.synthetic || s.data_origin==='Synthetic demo';
  const displayTitle=value=>String(value || '').replace(/\[SYNTHETIC\]\s*/gi,'').replace(/\bsynthetic\s+demo\s+consultant\b/gi,'Consultant').replace(/\bDEMO-/gi,'').replace(/\b(?:synthetic|demo)\b/gi,'').replace(/ {2,}/g,' ').trim();
  const quality=s=>s.evidence_quality==='Unresolved findings'?'Unresolved findings':s.solution_kind==='Workaround'?'Workaround':s.validation==='Verified'?'Verified fix':['Reviewed','Outdated'].includes(s.validation)?'Reviewed':'Unreviewed';
  function catalogPanel() {
    return `<section class="panel mt"><div class="panel-head"><div><h2>Historical documentation</h2><p>Past investigations, resolutions and known issues for current tickets.</p></div></div><div class="panel-body"><div class="action-row mt"><button class="btn primary" data-history="upload">Upload historical data</button><button class="btn" data-history="demo">Add reference library</button></div><p class="hint">Preview before saving. Reference library documents are available only to reference investigations. Indexing is a separate, explicit action.</p></div></section>`;
  }
  function filters(origin='All origins',evidence='All qualities',customer='All customers') {return `${select('history-customer','Customer',['All customers',...new Set(getState().sources.map(s=>s.customer).filter(Boolean).sort())],customer)}` + `${select('history-origin','Data origin',['All origins','User uploads','Reference library'],origin)}${select('history-quality','Evidence quality',['All qualities',...qualities],evidence)}`;}
  function labels(s) {return `${s.historical?badge(quality(s)):''}${s.simulated_quality?badge('Simulated '+s.simulated_quality):''}`;}
  async function read(file,sheet='') {
    if(file.size>5*1024*1024)throw Error('Files must be at most 5 MB.');
    const bytes=new Uint8Array(await file.arrayBuffer());let raw='';
    for(let i=0;i<bytes.length;i+=16384)raw+=String.fromCharCode(...bytes.subarray(i,i+16384));
    return api('/history/preview',{filename:file.name,file_base64:btoa(raw),sheet});
  }
  function uploadForm() {
    upload=null;selectedFile=null;
    openModal('Upload historical data',`<form id="history-upload-form"><label>Historical file<input name="file" type="file" required accept=".csv,.xlsx,.xlsm,.xltx,.pdf,.docx,.txt,.md,.html,.pptx,.json"></label><p class="hint">Up to 5 MB. CSV/XLSX imports support 1–100 records per batch. Documents become one source. No AI requests are used.</p><div class="form-actions"><button class="btn primary" type="submit">Preview historical data</button></div></form>`);
  }
  function previewForm() {
    const state=getState();
    const mapping=upload.mode==='table'?`<section><h3>Map historical fields</h3><p class="hint">Title and problem/content are required. Uncheck columns to exclude them; edit cells to redact sensitive data before saving. Only included columns are preserved. Blank mappings use the defaults below.</p><div class="field-grid">${Object.keys(upload.mapping).map(k=>`<label>${esc(k.replaceAll('_',' '))}${['title','content'].includes(k)?' *':''}<select name="map_${k}" ${['title','content'].includes(k)?'required':''}><option value="">Not mapped</option>${upload.headers.map(h=>option(h,upload.mapping[k])).join('')}</select></label>`).join('')}</div>${select('date_format','Date format',['ISO','MM/DD/YYYY','DD/MM/YYYY'],'ISO')}<details class="mt" open><summary>Preview all ${upload.rows.length} records</summary><div class="history-table"><table><thead><tr>${upload.headers.map(h=>`<th><label class="check"><input type="checkbox" name="include_column" value="${esc(h)}" checked>${esc(h)}</label></th>`).join('')}</tr></thead><tbody>${upload.rows.map((r,i)=>`<tr>${upload.headers.map((h,j)=>`<td><textarea name="cell_${i}_${j}" aria-label="${esc(h)} row ${i+1}">${esc(r[h])}</textarea></td>`).join('')}</tr>`).join('')}</tbody></table></div></details></section>`:`${input('title','Document title',upload.filename.replace(/\.[^.]+$/,''),true)}<label class="mt">Review extracted content<textarea name="content" required maxlength="120000" rows="10">${esc(upload.content)}</textarea></label>`;
    openModal('Review historical documentation',`${upload.sheets?.length>1?`<form id="history-sheet-form" class="action-row">${select('sheet','Worksheet',upload.sheets,upload.sheet)}<button class="btn" type="submit">Load worksheet</button></form>`:''}<form id="history-save-form"><p class="hint">Security screening: ${esc(upload.security_findings?.join(', ') || 'No patterns detected. Review content manually.')} · ${esc(upload.malware_scan || 'Malware scan status unknown')}</p>${mapping}<h3 class="mt">Classification and context</h3><div class="field-grid">${select('source_type','Document classification',kinds,upload.mode==='table'?'Historical ticket':'Investigation report')}${select('evidence_quality','Evidence quality',qualities,'Unreviewed')}${input('customer','Customer scope',state.customer,true)}${input('application','Application (default)', '',upload.mode!=='table')}${input('platform','SAP platform')}${input('module','SAP module')}${input('component','Component')}${input('version','System / release')}${input('document_version','Document version')}${input('source_reference','Original reference (default)')}<label>Original update date (default)<input name="source_updated_at" type="date"></label></div><label class="check mt"><input type="checkbox" name="synthetic"> Reference library content (excluded from customer tickets)</label><label class="check"><input type="checkbox" name="generalized_confirmed"> I removed customer-specific details before sharing as General knowledge.</label><label class="mt">Review notes / evidence references<textarea name="review_notes" maxlength="12000" placeholder="Required for Reviewed or Verified fix. Describe the evidence and its limitations."></textarea></label><div class="section-label">Verification evidence (required only for Verified fix)</div>${[['tested','Test evidence recorded'],['customer_confirmed','Customer confirmation recorded'],['deployed','Deployment evidence recorded']].map(([k,l])=>`<label class="check"><input type="checkbox" name="${k}">${l}</label>`).join('')}<p class="hint">Saving does not index or contact Gemini. Existing identical content in the same customer scope is skipped. Confirm source dates and review labels; ticket closure alone is not verification.</p><div class="form-actions"><button class="btn primary" type="submit">Save historical documentation</button></div></form>`);
  }
  function ticketPanel() {
    const t=getCurrent();const links=t.source_links || [];
    return `<section class="panel"><div class="panel-head"><div><h2>Historical references</h2><p>Search permitted source text locally. Attaching evidence does not select a solution or advance the lifecycle.</p></div></div><div class="panel-body">${t.lifecycle_stage==='Closure'?'<p>Recorded references are retained for this closed ticket.</p>':`<form id="history-search-form"><label>Search historical evidence<input name="query" required maxlength="500" placeholder="Symptoms, error, module or business process"></label><button class="btn mt" type="submit">Search without AI</button></form><div id="history-search-results" class="mt"></div>`}${links.map(r=>`<article class="gap-alert"><button class="source-ref" data-source="${esc(r.source_id)}">${esc(displayTitle(r.title))}</button>${badge(r.evidence_quality)}${r.synthetic?badge('Reference library'):''}${r.quote?`<blockquote>${esc(r.quote)}</blockquote>`:''}<p>${esc(r.reason)}</p><small>Attached by ${esc(r.attached_by)} · ${esc(r.attached_at)}</small></article>`).join('') || '<p class="hint">No historical references attached yet.</p>'}</div></section>`;
  }
  async function action(button) {
    const act=button.dataset.history;
    if(act==='upload')uploadForm();
    if(act==='demo')openModal('Reference library',`<p>Add 16 clearly labelled fictional documents covering batch expiry, vendor consistency, plant onboarding and quantity commitments. Includes simulated resolutions, workarounds, unresolved findings and outdated conflicting guidance.</p><p>Documents are saved unindexed. Rerunning preserves existing records and reviews. No AI requests are used.</p><button class="btn primary" data-history="install-demo">Add reference documents</button>`);
    if(act==='install-demo') {const r=await api('/history/demo',{});document.querySelector('#modal').close();await refresh();toast(`${r.saved.length} reference documents added; ${r.existing} already present. No AI requests used.`);}
    if(act==='attach') {
      const r=results[Number(button.dataset.result)];
      openModal('Attach historical evidence',`<form id="history-link-form"><input type="hidden" name="source_id" value="${esc(r.source_id)}"><h3>${esc(displayTitle(r.title))}</h3>${badge(r.evidence_quality)}${r.synthetic?badge('Reference library'):''}<label class="mt">Supporting quotation (optional)<textarea name="quote" maxlength="3000" rows="8">${esc(r.excerpt)}</textarea></label><label class="mt">Why is this relevant?<textarea name="reason" required maxlength="2000" placeholder="Describe applicability, differences or the question this evidence helps investigate."></textarea></label><p class="hint">Keep an exact quotation or leave it empty to link the whole source. This does not mark the source as an accepted fix.</p><div class="form-actions"><button class="btn primary" type="submit">Attach reference</button></div></form>`);
    }
    if(act==='index') {
      const plan=await api(`/sources/${button.dataset.id}/index-plan`,{});
      openModal('Review AI indexing',`<p>This sends the source text to Google Gemini to create search embeddings.</p><p><strong>${plan.chunks} chunks · ${plan.requests} estimated embedding request(s)</strong></p><p>ATLAS budget remaining: ${plan.quota.minute_remaining} this minute, ${plan.quota.daily_remaining} today. Upstream usage elsewhere may reduce availability.</p>${plan.already_indexed?'<p>This source is already indexed with the current model. Reindexing consumes the same estimated budget.</p>':''}<button class="btn primary" data-history="confirm-index" data-id="${esc(button.dataset.id)}">Send to Gemini and index</button>`);
    }
    if(act==='confirm-index') {
      const s=await api(`/sources/${button.dataset.id}/reindex`,{confirmed:true});await refresh();sourceModal(s.id);toast(s.index_status==='Ready'?'Indexing complete.':s.index_error);
    }
  }
  async function submit(form) {
    const data=Object.fromEntries(new FormData(form));
    if(form.id==='history-upload-form') {selectedFile=form.elements.file.files[0];upload=await read(selectedFile);previewForm();}
    if(form.id==='history-sheet-form') {upload=await read(selectedFile,data.sheet);previewForm();}
    if(form.id==='history-save-form') {
      const defaults={...data};for(const k of ['synthetic','generalized_confirmed','tested','customer_confirmed','deployed'])defaults[k]=form.elements[k].checked;
      const payload={filename:upload.filename,defaults};
      if(upload.mode==='table') {const included=new Set(new FormData(form).getAll('include_column'));payload.rows=upload.rows.map((r,i)=>Object.fromEntries(upload.headers.filter(h=>included.has(h)).map(h=>[h,data['cell_'+i+'_'+upload.headers.indexOf(h)]])));payload.mapping=Object.fromEntries(Object.keys(upload.mapping).map(k=>[k,included.has(data['map_'+k])?data['map_'+k]:'']));payload.date_format=data.date_format;}
      else payload.content=data.content;
      const r=await api('/history/import',payload);document.querySelector('#modal').close();await refresh();toast(`${r.saved.length} sources saved; ${r.duplicates.length} duplicates skipped. No AI requests used.`);
    }
    if(form.id==='history-search-form') {
      const r=await api(`/investigations/${getCurrent().id}/history-search`,data);results=r.results;
      document.querySelector('#history-search-results').innerHTML=results.length?results.map((s,i)=>`<article class="gap-alert"><button class="source-ref" data-source="${esc(s.source_id)}">${esc(displayTitle(s.title))}</button><div>${badge(s.evidence_quality)}${badge(s.validation)}${s.synthetic?badge('Reference library'):''}</div><p>${esc(s.version || 'Release unknown')} · Original date ${esc(s.source_updated_at || 'Unknown')}</p><p class="description">${esc(s.excerpt)}</p><button class="btn" data-history="attach" data-result="${i}">Attach as evidence</button></article>`).join(''):'<p>No permitted sources matched. Try different terms or upload relevant documentation.</p>';
      formatVisibleText(document.querySelector('#history-search-results'));
    }
    if(form.id==='history-link-form') {
      await api(`/investigations/${getCurrent().id}/source-link`,{...data,revision:getCurrent().revision});document.querySelector('#modal').close();await refresh();toast('Historical evidence attached. Lifecycle and selected solution are unchanged.');
    }
  }
  return {catalogPanel,filters,labels,ticketPanel,action,submit,isDemo,quality,displayTitle};
}
