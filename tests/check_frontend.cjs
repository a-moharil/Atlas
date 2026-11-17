// Pure UI logic checks; not a substitute for browser layout/playback testing.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const base=path.join(__dirname,'../static');
const nodes=new Map();function node(k){if(!nodes.has(k))nodes.set(k,{textContent:'',innerHTML:'',style:{setProperty(){}},classList:{add(){},remove(){},toggle(){}},prepend(){},querySelectorAll(){return []}});return nodes.get(k)}
const context={console,URL,URLSearchParams,AbortSignal,Date,Map,Set,Math,Number,String,Array,Object,JSON,document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){},documentElement:node('html'),createElement:()=>node('created')},window:{addEventListener(){},scrollTo(){}},location:{hash:'#news'},localStorage:{getItem(){return null}},setTimeout:()=>0,clearTimeout(){},setInterval:()=>0,fetch:async()=>({ok:true,json:async()=>({started:true})})};context.window.location=context.location;vm.createContext(context);
let script=fs.readFileSync(path.join(base,'atlas3.js'),'utf8');script=script.replace(/bootstrap\(\);?\s*$/,'');vm.runInContext(script,context);
vm.runInContext(`ROOT.metrics={timeline:[{time:'2026-11-16T10:10:00Z',success:1,failed:0,new:2}]};ROOT.state={entries:[],registry:{feeds:[],channels:[]},live_channels:[]};`,context);
assert(vm.runInContext('svgPlot()',context).includes('<circle'));
for(const fn of ['dashboard()','newsDesk("all")','newsDesk("india")','newsDesk("Technology")','newsDesk("Finance")','audit()','media()','research()','mapLayout()']) {const out=vm.runInContext(fn,context);assert(out.includes('<'),fn);assert(!out.includes('NaN'),fn)}
vm.runInContext('ROOT.view="india";refresh()',context).then(()=>{assert.equal(vm.runInContext('ROOT.view',context),'india');console.log('11 frontend logic checks passed: single-point plot, 9 panel renderers, refresh preserves page.');});
