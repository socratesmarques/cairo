const {test} = require('node:test');
const assert = require('node:assert/strict');
const {errorMessage, fetchJSON, shortcuts} = require('../cairo/web/client.js');
test('structured provider errors become readable text', async () => {
  assert.equal(errorMessage({error:{message:'Token inválido'}}, 401), 'Token inválido');
  await assert.rejects(fetchJSON('/test', {}, async () => ({ok:false,status:401,json:async()=>({error:{message:'Token inválido'}})})), /Token inválido/);
});
test('invalid JSON and offline network are actionable', async () => {
  await assert.rejects(fetchJSON('/test', {}, async () => ({ok:true,json:async()=>{throw new Error('invalid')}})), /resposta inválida/);
  await assert.rejects(fetchJSON('/test', {}, async () => {throw new TypeError('Failed to fetch')}), /conectar ao Cairo/);
});
test('requests time out without leaving a waiting promise', async () => {
  const fetcher = (_, options) => new Promise((resolve,reject) => options.signal.addEventListener('abort',()=>{const error=new Error('aborted');error.name='AbortError';reject(error);}));
  await assert.rejects(fetchJSON('/test',{timeoutMs:10},fetcher), /tempo limite/);
});
test('shortcuts are bounded, deduplicated and plain data', () => {
  assert.deepEqual(shortcuts([null,{name:'',prompt:'x'},{name:'A',prompt:'hello'},{name:'B',prompt:'hello'}]), [{name:'A',prompt:'hello'}]);
  assert.equal(shortcuts(Array.from({length:20},(_,i)=>({name:String(i),prompt:String(i)}))).length,12);
  assert.equal(shortcuts([{name:'<script>',prompt:'<img src=x onerror=alert(1)>'}])[0].name,'<script>');
  assert.deepEqual(shortcuts([{name:'A',prompt:'x'.repeat(16001)}]),[]);
});
