(function(root){
'use strict';
const sigmoid=x=>x>=0?1/(1+Math.exp(-x)):Math.exp(x)/(1+Math.exp(x));
function wallParts(ms,zone){const p=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(ms));return Object.fromEntries(p.filter(x=>x.type!=='literal').map(x=>[x.type,Number(x.value)]));}
function localUTC(value,zone){
 if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(value))throw Error('יש להזין תאריך ושעה מלאים לכל אירוע.');
 const nominal=Date.parse(value+':00Z');
 if(!Number.isFinite(nominal)||new Date(nominal).toISOString().slice(0,16)!==value)throw Error('תאריך או שעה אינם תקינים.');
 const offsets=new Set();
 for(let h=-36;h<=36;h+=6){let ms=nominal+h*3600000;let p=wallParts(ms,zone);offsets.add(Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute)-ms);}
 const wanted=value.replace('T','-').split(/[-:]/).map(Number),candidates=[];
 for(const offset of offsets){let ms=nominal-offset,p=wallParts(ms,zone);if([p.year,p.month,p.day,p.hour,p.minute].every((n,i)=>n===wanted[i]))candidates.push(ms);}
 if(candidates.length!==1)throw Error('השעה המקומית חסרה או דו־משמעית עקב מעבר שעון קיץ. יש לבחור זמן חד־משמעי או לבדוק את פרטי המקור.');
 return candidates[0];
}
function predict(features,model){
 let previous=0;const risks={};
 for(const t of ['30','45','60']){
  const m=model.models[t];let raw;
  if(m.selected==='constant_train_rate')raw=m.default;
  else if(m.selected==='gap_empirical')raw=m.gap_rates[String(Math.floor(features.gap_minutes/15))]??m.default;
  else{
   let linear=m.intercept,index=0;
   model.categorical.forEach((name,i)=>m.categories[i].forEach(cat=>{if(features[name]===cat)linear+=m.coefficient[index];index++;}));
   model.numeric.forEach((name,i)=>{linear+=m.coefficient[index++]*((features[name]-m.mean[i])/m.scale[i]);});raw=sigmoid(linear);
  }
  raw=Math.max(1e-6,Math.min(1-1e-6,raw));const calibrated=sigmoid(m.calibration_slope*Math.log(raw/(1-raw))+m.calibration_intercept);
  risks[t]=Math.max(previous,calibrated);previous=risks[t];
 }
 return risks;
}
function assess(input,model){
 if(!input.sharedTicket)throw Error('הגרסה הזו מיועדת לחיבור שמוצע בכרטיס משותף. יש לאשר זאת לפי מקור ההצעה.');
 const first=input.first,second=input.second;
 for(const f of [first,second]){
  if(!/^[A-Z0-9]{2}$/.test(f.carrier)||!/^\d{1,4}$/.test(f.number)||Number(f.number)===0)throw Error('יש להזין קוד חברה בן שני תווים ומספר טיסה בן 1–4 ספרות.');
  for(const code of [f.origin,f.destination])if(!model.airports[code])throw Error('אין כיסוי למיפוי שדה התעופה '+code+'. נדרשות טיסות פנים בארה״ב ושדות בכיסוי המודל.');
 }
 if(first.destination!==second.origin)throw Error('שדה הנחיתה של הטיסה הראשונה שונה משדה ההמראה של השנייה. החלפת שדה אינה נתמכת.');
 if(!model.hubs.includes(first.destination))throw Error('שדה המעבר אינו בכיסוי המחקר. כרגע נתמכים ATL, ORD ו־DFW.');
 if(first.carrier!==second.carrier)throw Error('המודל הנוכחי נבדק רק בזוגות באותה חברה מדווחת. חיבור בין חברות אינו נתמך.');
 if(Number(first.number)===Number(second.number))throw Error('המשך באותו מספר טיסה אינו בכיסוי המחקר הנוכחי.');
 if(first.origin===second.destination||first.origin===first.destination||second.origin===second.destination)throw Error('נדרש מסלול עם החלפת טיסה וללא חזרה לשדה המוצא.');
 const categories=model.models['45'].categories;
 for(const [i,value] of [[0,first.origin],[1,first.destination],[2,second.destination],[3,first.carrier]])if(!categories[i].includes(value))throw Error('אין כיסוי אימון לשדה או לחברה שבחרתם; לא תוצג הסתברות.');
 const a=localUTC(first.departure,model.airports[first.origin].timezone),b=localUTC(first.arrival,model.airports[first.destination].timezone),c=localUTC(second.departure,model.airports[second.origin].timezone),d=localUTC(second.arrival,model.airports[second.destination].timezone);
 for(const [dep,arr] of [[a,b],[c,d]])if(arr<=dep||arr-dep>24*3600000)throw Error('זמני הטיסה אינם עקביים: ההגעה חייבת להיות אחרי היציאה, ומשך כל רגל עד 24 שעות.');
 const gap=(c-b)/60000,duration=(d-a)/60000;
 if(gap<30||gap>240)throw Error('מרווח המעבר הוא '+gap+' דקות. המודל נבדק רק למרווחים של 30–240 דקות; לא תוצג הסתברות מחוץ לטווח.');
 const dt=new Date(a),hour=Number(first.departure.slice(11,13)),weekday=(dt.getUTCDay()+6)%7,month=dt.getUTCMonth()+1;
 const features={origin:first.origin,hub:first.destination,destination:second.destination,carrier:first.carrier,gap_minutes:gap,duration_minutes:duration};
 for(const [name,value,period] of [['hour',hour,24],['week',weekday,7],['year',month,12]]){features[name+'_sin']=Math.sin(2*Math.PI*value/period);features[name+'_cos']=Math.cos(2*Math.PI*value/period);}
 const day=first.departure.slice(0,10);
 return {gap,duration,risks:predict(features,model),features,withinDemoPeriod:day>=model.validated_start&&day<=model.validated_end,timesUTC:[a,b,c,d].map(x=>new Date(x).toISOString()),source:'manual_unverified',version:model.version};
}
const api={localUTC,predict,assess};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ConnectionChecker=api;
})(typeof window!=='undefined'?window:{});
