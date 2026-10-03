export class MemoryExecutionLedger {
  constructor({clock,trace}={}){this.clock=clock;this.trace=trace;this.rows=[];this.seq=0;}
  append(entry){
    const row=Object.freeze({ledgerSeq:++this.seq,atMs:this.clock?.now?.()??Date.now(),...structuredClone(entry)});
    this.rows.push(row);this.trace?.record('ledger.append',row);return row;
  }
  entries(){return [...this.rows];}
  findByAction(actionId){return this.rows.filter(x=>x.actionId===actionId);}
  clear(){this.rows.length=0;this.seq=0;}
}
