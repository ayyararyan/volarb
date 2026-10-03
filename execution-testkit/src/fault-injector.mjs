export class FaultInjector {
  constructor(rules=[]){this.rules=rules.map((r,i)=>({...structuredClone(r),_id:i,_hits:0}));}
  add(rule){this.rules.push({...structuredClone(rule),_id:this.rules.length,_hits:0});}
  match({operation,phase,context={}}){
    for(const rule of this.rules){
      if(rule.operation&&rule.operation!==operation) continue;
      if(rule.phase&&rule.phase!==phase) continue;
      if(rule.correlationId&&rule.correlationId!==context.correlationId) continue;
      rule._hits++;
      if(rule.occurrence&&rule._hits!==rule.occurrence) continue;
      if(rule.once&&rule._fired) continue;
      rule._fired=true;
      return rule;
    }
    return null;
  }
}
