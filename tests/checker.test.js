const assert=require('node:assert/strict');
const fs=require('node:fs');
const core=require('../app/checker-core.js');
const model=JSON.parse(fs.readFileSync('app/checker-model.json','utf8'));
assert.equal(core.localUTC('2025-01-01T23:00','America/Chicago'),Date.parse('2025-01-02T05:00Z'));
assert.equal(core.localUTC('2025-07-01T12:00','America/New_York'),Date.parse('2025-07-01T16:00Z'));
for(const time of ['2025-03-09T02:30','2025-11-02T01:30','2025-02-30T12:00'])assert.throws(()=>core.localUTC(time,'America/New_York'));
const example={sharedTicket:true,first:{carrier:'AA',number:'123',origin:'JFK',destination:'ORD',departure:'2025-10-22T10:00',arrival:'2025-10-22T12:00'},second:{carrier:'AA',number:'456',origin:'ORD',destination:'LAX',departure:'2025-10-22T13:15',arrival:'2025-10-22T15:30'}};
let result=core.assess(example,model);assert.equal(result.gap,75);assert.equal(result.duration,510);assert.ok(result.risks['30']<=result.risks['45']&&result.risks['45']<=result.risks['60']);
function invalid(fn){const input=structuredClone(example);fn(input);assert.throws(()=>core.assess(input,model));}
invalid(x=>x.sharedTicket=false);invalid(x=>x.second.origin='DFW');invalid(x=>x.second.carrier='DL');invalid(x=>x.first.destination='DEN');invalid(x=>x.second.departure='2025-10-22T12:15');invalid(x=>x.first.arrival='2025-10-22T08:00');invalid(x=>x.second.number='0123');invalid(x=>x.first.origin='ZZZ');
let future=structuredClone(example);for(const f of [future.first,future.second]){f.departure=f.departure.replace('2025-10-22','2027-10-22');f.arrival=f.arrival.replace('2025-10-22','2027-10-22');}assert.equal(core.assess(future,model).withinDemoPeriod,false);
if(process.argv[2]){const fixtures=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));for(const row of fixtures){const p=core.predict(row.features,model);for(const t of ['30','45','60'])assert.ok(Math.abs(p[t]-row.expected[t])<1e-10,`${t}: ${p[t]} != ${row.expected[t]}`);}console.log(`Exact Python/JavaScript probability parity: ${fixtures.length} historical cases.`);}
console.log('Checker: DST, invalid dates, overnight times, route/carrier/ticket/coverage guards and future-date flag passed.');
