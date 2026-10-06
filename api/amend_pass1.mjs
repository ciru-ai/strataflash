// Recompute the pinned verifier score from 19 original cases and authorized HA-04.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const root=path.dirname(new URL(import.meta.url).pathname);
const profile='Token Plan Qwen3.8 Flash';
const source='evidence/ciru/runs/20260929-flash-hermes-unlimited/HermesAgent-20/dist/lib/benchmark.js';
const {scoreModelResults}=require(source);
function summary(stage){
  const folders=fs.readdirSync(path.join(root,stage,'cases'));
  if(folders.length!==1)throw Error('Expected one case run');
  return JSON.parse(fs.readFileSync(path.join(root,stage,'cases',folders[0],'summary.json')));
}
const initial=summary('hermes-pass1');
const continued=summary('hermes-pass1-continuation');
const corrected=summary('hermes-pass1-ha04-correction');
if(corrected.status!=='completed')throw Error('Correction must complete');
const replacement=corrected.resultsByModel[profile];
if(replacement.length!==1 || replacement[0].scenarioId!=='HA-04')throw Error('Only authorized case may be replaced');
const cases=[...initial.resultsByModel[profile].filter(x=>x.scenarioId!=='HA-04'),...continued.resultsByModel[profile],...replacement].sort((a,b)=>a.scenarioId.localeCompare(b.scenarioId));
const expected=Array.from({length:20},(_,i)=>`HA-${String(i+1).padStart(2,'0')}`);
if(JSON.stringify(cases.map(x=>x.scenarioId))!==JSON.stringify(expected))throw Error('Require all20 exactly once in selected score');
const result={...initial,status:'completed',scenarioCount:20,resultsByModel:{[profile]:cases},scores:{[profile]:scoreModelResults(cases)},
  completedAt:new Date().toISOString(),reconstructedFromSavedCases:true,authorization:'User explicitly requested retry4 with corrected adapter and amend pass1',
  amendedCase:'HA-04',originalFailedAttemptPreserved:true,selectedAttemptCounts:{original:19,authorizedCorrection:1},
  sources:['hermes-pass1','hermes-pass1-continuation','hermes-pass1-ha04-correction'],
  scoredCaseWallSeconds:cases.reduce((n,x)=>n+(x.timings?.durationMs||0)/1000,0)};
fs.mkdirSync(path.join(root,'amended-pass1'),{recursive:true});
fs.writeFileSync(path.join(root,'amended-pass1/summary.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({selectedCases:20,score:result.scores[profile],wallSeconds:result.scoredCaseWallSeconds}));
