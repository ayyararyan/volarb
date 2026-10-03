export class VirtualClock {
  constructor(startMs=0){
    if(!Number.isFinite(startMs)) throw new TypeError('startMs must be finite');
    this.time=startMs;this.seq=0;this.queue=[];this.cancelled=new Set();
  }
  now(){return this.time;}
  schedule(delayMs,fn,{label=null}={}){
    if(!Number.isFinite(delayMs)||delayMs<0) throw new TypeError('delayMs must be >= 0');
    if(typeof fn!=='function') throw new TypeError('scheduled callback must be a function');
    const task={id:++this.seq,at:this.time+delayMs,seq:this.seq,fn,label};
    this.queue.push(task);this.queue.sort((a,b)=>a.at-b.at||a.seq-b.seq);return task.id;
  }
  scheduleAt(atMs,fn,options={}){return this.schedule(atMs-this.time,fn,options);}
  cancel(id){this.cancelled.add(id);}
  pending(){return this.queue.filter(x=>!this.cancelled.has(x.id)).map(x=>({id:x.id,at:x.at,label:x.label}));}
  async advance(ms){
    if(!Number.isFinite(ms)||ms<0) throw new TypeError('advance ms must be >= 0');
    const target=this.time+ms;
    while(true){
      this.queue.sort((a,b)=>a.at-b.at||a.seq-b.seq);
      const next=this.queue.find(x=>!this.cancelled.has(x.id)&&x.at<=target);
      if(!next) break;
      this.queue=this.queue.filter(x=>x.id!==next.id);
      this.time=next.at;
      await next.fn();
    }
    // A callback may advance the shared clock while awaiting a broker delay.
    // Returning to the outer advance must never rewind that elapsed time.
    this.time=Math.max(this.time,target);
    return this.time;
  }
  async runUntilIdle({maxEvents=100000}={}){
    let count=0;
    while(this.pending().length){
      if(++count>maxEvents) throw new Error('VirtualClock maxEvents exceeded');
      const next=this.pending()[0];
      await this.advance(next.at-this.time);
    }
    return count;
  }
}
