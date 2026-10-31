const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const app = path.resolve(__dirname, "..");
const bench = path.resolve(app, "../../..");
const script = process.env.LIST_RESIZE_SCRIPT || path.join(app, "public/js/enhanced_list_view/enhanced_list_view.js");
const css = process.env.LIST_RESIZE_CSS || path.join(app, "public/css/enhanced_list_view/enhanced_list_view.css");
const jquery = path.resolve(app, "../../frappe/node_modules/jquery/dist/jquery.js");
const native_source = fs.readFileSync(
	path.resolve(app, "../../frappe/frappe/public/js/frappe/list/list_view.js"),
	"utf8"
);
const native_headers = native_source.slice(
	native_source.indexOf("\tget_header_html() {"),
	native_source.indexOf("\n\tget_left_html(doc) {")
);
const desk_dir = path.join(bench, "sites/assets/frappe/dist/css");
const desk_css = path.join(
	desk_dir,
	fs.readdirSync(desk_dir).find((file) => /^desk\.bundle\..*\.css$/.test(file))
);

function fixture() {
	return `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="file://${desk_css}">
<link rel="stylesheet" href="file://${css}">
<style>body{display:block;padding:24px}.result{width:900px;max-width:100%}section{margin-bottom:24px}#results,.grid-row{display:none}</style>
<script src="file://${jquery}"></script></head><body>
<div class="grid-row" draggable="true">Form child table</div><pre id="results"></pre>
<script>
window.addEventListener('error',event=>document.getElementById('results').textContent=JSON.stringify({ok:false,error:event.message}));
window.requestAnimationFrame=callback=>setTimeout(callback,0);
window.__=text=>text;
const settings={}; let child_drags=0, user='A';
document.querySelector('.grid-row').addEventListener('dragstart',()=>child_drags++);
const fields={name:{fieldname:'name',label:'ID'},supplier:{fieldname:'supplier',label:'Supplier'},customer:{fieldname:'customer',label:'Customer'},grand_total:{fieldname:'grand_total',label:'Grand Total',fieldtype:'Currency'}};
class ListView {
 constructor(doctype,view='List') {
  this.doctype=doctype;this.view_name=view;this.party=doctype==='Purchase Invoice'?'supplier':'customer';this.settings={};this.saved=0;this.sorted=0;
  this.$frappe_list=$('<section>').appendTo('body');$('<h4>').text(doctype+' '+view).appendTo(this.$frappe_list);
  this.$result=$('<div class="result no-assign-to">').appendTo(this.$frappe_list);this.page=1;
  this.$result.on('click','[data-sort-by]',()=>this.sorted++);
 }
 setup_columns() {this.columns=[{type:'Subject',df:fields.name},{type:'Status'},{type:'Field',df:fields[this.party]},{type:'Field',df:fields.grand_total}];}
 ${native_headers}
 render_header() {this.$result.find('.list-row-head').closest('.list-row-container').remove();this.$result.prepend(this.get_header_html());return 'header';}
 render_list() {
  this.$result.find('.list-row').closest('.list-row-container').remove();this.render_header();
  this.$result.append('<div class="list-row-container"><div class="list-row level"><div class="level-left ellipsis">'+
   '<div class="list-row-col list-subject level"><span class="level-item select-like"><input type="checkbox" class="list-row-checkbox"></span><span class="level-item ellipsis"><a href="/app/'+this.doctype.toLowerCase().replaceAll(' ','-')+'/TEST-'+this.page+'">TEST-'+this.page+'</a></span></div>'+
   '<div class="list-row-col hidden-xs ellipsis"><span class="indicator-pill green">Paid</span></div>'+
   '<div class="list-row-col hidden-xs ellipsis">Example party</div><div class="list-row-col text-right hidden-xs ellipsis">AED 77.88</div>'+
   '</div><div class="level-right text-muted ellipsis"><span>1 hour ago</span></div></div></div>');return 'rows';
 }
 get_menu_items(){return [{label:'Native Menu'}];}
 save_view_user_settings(value){this.saved++;Object.assign(settings[user][this.doctype].List,value);return Promise.resolve();}
}
const native={header:ListView.prototype.get_header_html,columns:ListView.prototype.setup_columns,menu:ListView.prototype.get_menu_items};
window.frappe={views:{ListView},is_mobile:()=>false,get_user_settings:(dt,view)=>settings[user]?.[dt]?.[view],model:{is_numeric_field:df=>df?.fieldtype==='Currency'},msgprint:message=>{throw new Error(message)}};
</script><script src="file://${script}"></script><script src="file://${script}"></script><script>
(async()=>{
 await document.fonts.ready;
 const results=[]; const check=(condition,message)=>{if(!condition)throw new Error(message)};
 const wait=()=>new Promise(resolve=>setTimeout(resolve,25));
 const pointer=(target,type,x)=>target.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,button:0,clientX:x,pointerId:4}));
 const widths={name:240,status_field:100,supplier:280,customer:280,grand_total:160};
 const css_props=['fontFamily','fontSize','fontWeight','lineHeight','height','paddingTop','paddingBottom','marginRight'];
 const style_values=element=>{const style=getComputedStyle(element);return css_props.map(key=>style[key]).join('|')};
 check(native.header===ListView.prototype.get_header_html && native.columns===ListView.prototype.setup_columns && native.menu===ListView.prototype.get_menu_items,'Native methods replaced');
 for(const doctype of ['Sales Invoice','Purchase Invoice','Customer']) {
  settings.A=settings.A||{};settings.A[doctype]={List:{enhanced_list_view:{custom_columns:true,columns:[{fieldname:'grand_total',width:130,order:0}],widths:{...widths}}}};
  const list=new ListView(doctype);list.setup_columns();list.render_list();
  const row_before=style_values(list.$result.find('.list-row')[0]);
  const head_before=style_values(list.$result.find('.list-row-head')[0]);
  const check_before=style_values(list.$result.find('.list-row-checkbox')[0]);
  const indicator_before=style_values(list.$result.find('.indicator-pill')[0]);
  const verify=async()=>{
   await wait();const root=list.$result[0];
   check(list.$result.find('.cmelv-resize-line').length===4,doctype+': duplicate/missing handles');
   check(!root.textContent.includes('Drag'),doctype+': badge');
   const heads=list.$result.find('.list-header-subject>[data-cmelv-index]').toArray();
   const cells=list.$result.find('.list-row .level-left>[data-cmelv-index]').toArray();
   heads.forEach((head,index)=>{const h=head.getBoundingClientRect(),c=cells[index].getBoundingClientRect();check(Math.abs(h.x-c.x)<0.6&&h.width===c.width,doctype+': alignment '+index+' '+h.x+'/'+c.x);});
   check(style_values(list.$result.find('.list-row')[0])===row_before,doctype+': native row styling');
   check(style_values(list.$result.find('.list-row-head')[0])===head_before,doctype+': native header styling');
   check(style_values(list.$result.find('.list-row-checkbox')[0])===check_before,doctype+': checkbox styling');
   check(style_values(list.$result.find('.indicator-pill')[0])===indicator_before,doctype+': status styling');
   return heads;
  };
  let heads=await verify();check(heads[3].getBoundingClientRect().width===160,doctype+': width map precedence');
  check(list.columns[1].type==='Status',doctype+': native order');
  const handle=heads[2].querySelector('.cmelv-resize-line');
  check(getComputedStyle(handle).cursor==='col-resize',doctype+': cursor');
  check(getComputedStyle(handle,'::after').width==='1px',doctype+': thin boundary');
  pointer(handle,'pointerdown',100);pointer(document,'pointermove',250);await verify();
  check(heads[2].getBoundingClientRect().width===430,doctype+': live grow');
  const grown_width=parseFloat(list.$result[0].style.getPropertyValue('--cmelv-row-width'));
  pointer(document,'pointerup',250);handle.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));await wait();
  check(list.saved===1&&list.sorted===0,doctype+': resize sorting or duplicate save');
  heads=await verify();pointer(handle,'pointerdown',250);pointer(document,'pointermove',200);pointer(document,'pointerup',200);await wait();
  check(heads[2].getBoundingClientRect().width===380,doctype+': shrink');
  check(parseFloat(list.$result[0].style.getPropertyValue('--cmelv-row-width'))===grown_width-50,doctype+': shrink content width without feedback');
  pointer(handle,'pointerdown',0);pointer(document,'pointermove',-2000);pointer(document,'pointerup',-2000);await wait();
  check(heads[2].getBoundingClientRect().width===96,doctype+': minimum');
  pointer(handle,'pointerdown',0);pointer(document,'pointermove',850);pointer(document,'pointerup',850);await wait();await verify();
  check(list.$result[0].scrollWidth>list.$result[0].clientWidth,doctype+': horizontal overflow');
  list.$result[0].scrollLeft=200;check(list.$result[0].scrollLeft===200,doctype+': horizontal scrolling');await verify();
  check(settings.A[doctype].List.enhanced_list_view.widths[list.party]===946,doctype+': saved width');
  const beforeCancel=heads[2].getBoundingClientRect().width;pointer(handle,'pointerdown',0);pointer(document,'pointermove',-200);pointer(document,'pointercancel',-200);await wait();
  check(heads[2].getBoundingClientRect().width===beforeCancel,doctype+': cancel restores width');
  list.render_header();list.render_list();await verify();
  const stable_width=list.$result[0].style.getPropertyValue('--cmelv-row-width');
  list.render_header();list.render_list();await verify();check(list.$result[0].style.getPropertyValue('--cmelv-row-width')===stable_width,doctype+': no width drift after render');
  list.filter='Paid';list.render_list();await verify();list.page++;list.render_list();await verify();
  list.$result.find('[data-sort-by=grand_total]').trigger('click');check(list.sorted===1,doctype+': native sorting');
  list.$result.find('.list-row-checkbox').prop('checked',true).trigger('change');check(list.$result.find('.list-row-checkbox').prop('checked'),doctype+': checkbox');
  check(list.$result.find('a')[0].getAttribute('href').endsWith('/TEST-2'),doctype+': document link');
  const routed=new ListView(doctype);routed.setup_columns();routed.render_list();await wait();check(routed.$result.find('.list-header-subject>[data-cmelv-index="2"]').width()===946,doctype+': route persistence');
  const other=new ListView(doctype,'Report');other.setup_columns();other.render_list();await wait();check(!other.$result.find('.cmelv-resize-line').length,doctype+': other view');
  routed.view_name='Report';routed.render_list();await wait();check(!routed.$result[0].classList.contains('cmelv-resizable')&&!routed.$result.find('.cmelv-resize-line').length,doctype+': reused view cleanup');
  routed.$frappe_list.remove();other.$frappe_list.remove();
  list.$result[0].scrollLeft=0;
  results.push({doctype,native_style:true,grow_shrink:true,alignment:true,sorting:true,scrolling:true,persistence:true});
 }
 user='B';settings.B={'Sales Invoice':{List:{}}};const other_user=new ListView('Sales Invoice');other_user.setup_columns();other_user.render_list();await wait();
 check(other_user.$result.find('.list-header-subject>[data-cmelv-index="2"]').width()!==946,'User settings isolation');other_user.$frappe_list.remove();
 const grid=document.querySelector('.grid-row');grid.dispatchEvent(new DragEvent('dragstart',{bubbles:true}));check(grid.draggable&&child_drags===1,'Child grid isolation');
 document.getElementById('results').textContent=JSON.stringify({ok:true,results});
})().catch(error=>document.getElementById('results').textContent=JSON.stringify({ok:false,error:error.stack}));
</script></body></html>`;
}

test("native List View rendering with width-only resize, alignment and persistence", () => {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cm-list-resize-"));
	try {
		const file = path.join(dir, "list.html");
		fs.writeFileSync(file, fixture());
		const result = spawnSync(
			process.env.CHROME_BIN || "/usr/bin/google-chrome",
			[
				"--headless",
				"--no-sandbox",
				"--disable-gpu",
				"--disable-dev-shm-usage",
				"--no-first-run",
				"--allow-file-access-from-files",
				...(process.env.LIST_RESIZE_SCREENSHOT
					? [`--screenshot=${process.env.LIST_RESIZE_SCREENSHOT}`]
					: []),
				`--user-data-dir=${path.join(dir, "profile")}`,
				"--window-size=1440,1400",
				"--virtual-time-budget=10000",
				"--dump-dom",
				`file://${file}`,
			],
			{ encoding: "utf8", timeout: 30000, maxBuffer: 4 * 1024 * 1024 }
		);
		assert.equal(result.status, 0, result.stderr || String(result.error));
		const match = result.stdout.match(/<pre id="results">([^<]+)<\/pre>/);
		assert.ok(match, "Browser fixture did not finish");
		const output = JSON.parse(
			match[1].replaceAll("&gt;", ">").replaceAll("&lt;", "<").replaceAll("&amp;", "&")
		);
		assert.equal(output.ok, true, output.error);
		assert.deepEqual(
			output.results.map((row) => row.doctype),
			["Sales Invoice", "Purchase Invoice", "Customer"]
		);
	} finally {
		fs.rmSync(dir, { recursive: true, force: true });
	}
});

test("Desk hooks load only fingerprinted entries for the single width-only implementation", () => {
	const hooks = fs.readFileSync(path.join(app, "hooks.py"), "utf8");
	for (const extension of ["js", "css"]) {
		const bundle = `construction_list_view.bundle.${extension}`;
		assert.equal(hooks.split(`"${bundle}"`).length - 1, 1);
		assert.ok(!hooks.includes(`/assets/construction_management/${extension}/enhanced_list_view/`));
	}
	assert.match(fs.readFileSync(path.join(app, "public/js/construction_list_view.bundle.js"), "utf8"), /import "\.\/enhanced_list_view\/enhanced_list_view\.js"/);
	assert.match(fs.readFileSync(path.join(app, "public/css/construction_list_view.bundle.scss"), "utf8"), /@use "\.\/enhanced_list_view\/enhanced_list_view\.css"/);
	const implementation = fs.readFileSync(path.join(app, "public/js/enhanced_list_view/enhanced_list_view.js"), "utf8");
	assert.ok(implementation.includes("__cmelv_widths_only"));
	for (const token of ["cmelv-drag-handle", "dragover", "drop", '__("Drag")'])
		assert.ok(!implementation.includes(token));
});
