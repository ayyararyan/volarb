function key(ref){
  if(typeof ref==='string') return ref;
  const r=ref?.providerInstrumentRef??ref??{};
  return [r.provider??'',r.providerInstrumentId??r.securityId??r.symbol??'',r.exchangeSegment??''].join(':');
}
export class SimulatedMarket {
  constructor({clock,trace}={}){this.clock=clock;this.trace=trace;this.quotes=new Map();this.listeners=new Set();}
  setQuote(instrument,quote){
    const k=key(instrument),value=Object.freeze({...structuredClone(quote),instrument:structuredClone(instrument),observedAtMs:this.clock?.now?.()??Date.now()});
    this.quotes.set(k,value);this.trace?.record('market.quote',value);
    for(const listener of this.listeners) listener(value);
    return value;
  }
  snapshot(instruments=null){
    if(instruments===null) return [...this.quotes.values()];
    return instruments.map(x=>this.quotes.get(key(x))).filter(Boolean);
  }
  subscribe(listener){this.listeners.add(listener);return()=>this.listeners.delete(listener);}
  scheduleQuote(atMs,instrument,quote){
    if(!this.clock) throw new Error('SimulatedMarket requires a clock for scheduled quotes');
    return this.clock.scheduleAt(atMs,()=>this.setQuote(instrument,quote),{label:'market.quote'});
  }
}
export const instrumentKey=key;
