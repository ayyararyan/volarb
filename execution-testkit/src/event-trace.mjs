function clone(value){return value===undefined?undefined:structuredClone(value);}
export class EventTrace {
  constructor({clock}={}){this.clock=clock;this.events=[];this.seq=0;}
  record(type,payload={}){
    const event=Object.freeze({seq:++this.seq,timeMs:this.clock?.now?.()??Date.now(),type,payload:clone(payload)});
    this.events.push(event);return event;
  }
  all(){return [...this.events];}
  ofType(type){return this.events.filter(x=>x.type===type);}
  count(type){return this.ofType(type).length;}
  clear(){this.events.length=0;this.seq=0;}
}
