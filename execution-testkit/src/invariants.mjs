export class InvariantViolation extends Error {
  constructor(name,message,event=null){super(`${name}: ${message}`);this.name='InvariantViolation';this.invariant=name;this.event=event;}
}
const byOrder=events=>{
  const map=new Map();
  for(const e of events){const k=e.payload?.orderRef;if(!k)continue;if(!map.has(k))map.set(k,[]);map.get(k).push(e);}
  return map;
};
export function noOverfill(events){
  for(const [orderRef,rows] of byOrder(events.filter(x=>x.type==='broker.fill'))){
    const filled=rows.reduce((n,x)=>n+Number(x.payload.quantity||0),0);
    const requested=Math.max(...rows.map(x=>Number(x.payload.requestedQuantity||0)));
    if(filled>requested) throw new InvariantViolation('NO_OVERFILL',`${orderRef} filled ${filled} > requested ${requested}`,rows.at(-1));
  }
}
export function ledgerBeforeMutation(events){
  const ledgerSeqByAction=new Map();
  for(const e of events.filter(x=>x.type==='ledger.append'&&x.payload?.actionId)){
    if(!ledgerSeqByAction.has(e.payload.actionId)) ledgerSeqByAction.set(e.payload.actionId,e.seq);
  }
  for(const e of events.filter(x=>x.type==='broker.command.applied')){
    if(!e.payload?.actionId) throw new InvariantViolation('LEDGER_BEFORE_MUTATION','broker mutation has no action identity',e);
    const seq=ledgerSeqByAction.get(e.payload.actionId);
    if(!seq||seq>=e.seq) throw new InvariantViolation('LEDGER_BEFORE_MUTATION',`action ${e.payload.actionId} reached broker before durable intent`,e);
  }
}
export function noBlindRetryAfterAmbiguity(events){
  const ambiguous=new Map();
  for(const e of events){
    const corr=e.payload?.correlationId;if(!corr)continue;
    if(e.type==='broker.command.ambiguous') ambiguous.set(corr,e.seq);
    if(e.type==='recovery.reconciled') ambiguous.delete(corr);
    if(e.type==='broker.command.applied'&&e.payload.operation==='PLACE_ORDER'&&ambiguous.has(corr)&&e.seq>ambiguous.get(corr)){
      throw new InvariantViolation('NO_BLIND_RETRY_AFTER_AMBIGUITY',`correlation ${corr} was placed again before reconciliation`,e);
    }
  }
}
export function noStaleIntentMutation(events){
  const active=new Map();
  for(const e of events){
    if(e.type==='intent.active') active.set(e.payload.intentId,e.payload.intentVersion);
    if(e.type==='broker.command.applied'&&e.payload.intentId&&e.payload.intentVersion!==null){
      const current=active.get(e.payload.intentId);
      if(current!==undefined&&e.payload.intentVersion!==current) throw new InvariantViolation('NO_STALE_INTENT_MUTATION',`intent ${e.payload.intentId} version ${e.payload.intentVersion} != active ${current}`,e);
    }
  }
}
export const DEFAULT_INVARIANTS=Object.freeze([noOverfill,ledgerBeforeMutation,noBlindRetryAfterAmbiguity,noStaleIntentMutation]);
export function checkInvariants(events,invariants=DEFAULT_INVARIANTS){for(const invariant of invariants) invariant(events);return true;}
