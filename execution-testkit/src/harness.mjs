import { VirtualClock } from './virtual-clock.mjs';
import { SeededRng } from './seeded-rng.mjs';
import { EventTrace } from './event-trace.mjs';
import { MemoryExecutionLedger } from './memory-ledger.mjs';
import { SimulatedMarket } from './simulated-market.mjs';
import { FaultInjector } from './fault-injector.mjs';
import { SimulatedBroker } from './simulated-broker.mjs';
import { checkInvariants, DEFAULT_INVARIANTS } from './invariants.mjs';

export function createExecutionTestbed({
  startMs=0,seed=1,funds,positions,orders,trades,brokerScripts={},faultRules=[],marginCalculator
}={}){
  const clock=new VirtualClock(startMs);
  const trace=new EventTrace({clock});
  const rng=new SeededRng(seed);
  const ledger=new MemoryExecutionLedger({clock,trace});
  const market=new SimulatedMarket({clock,trace});
  const faults=new FaultInjector(faultRules);
  const broker=new SimulatedBroker({clock,trace,market,faults,funds,positions,orders,trades,scripts:brokerScripts,marginCalculator});
  return Object.freeze({clock,trace,rng,ledger,market,faults,broker});
}

export class ComponentHarness {
  constructor({componentFactory,testbed=createExecutionTestbed(),overrides={}}){
    if(typeof componentFactory!=='function') throw new TypeError('componentFactory must be a function');
    this.testbed=testbed;
    this.dependencies={broker:testbed.broker,market:testbed.market,clock:testbed.clock,ledger:testbed.ledger,rng:testbed.rng,trace:testbed.trace,...overrides};
    this.component=componentFactory(this.dependencies);
  }
  async invoke(method,input){
    if(typeof this.component?.[method]!=='function') throw new TypeError(`component does not implement ${method}()`);
    this.testbed.trace.record('harness.invoke',{method,input});
    const output=await this.component[method](input);
    this.testbed.trace.record('harness.result',{method,output});
    return output;
  }
}

export class CompositionHarness {
  constructor({componentFactories,testbed=createExecutionTestbed(),overrides={}}){
    if(!componentFactories||typeof componentFactories!=='object') throw new TypeError('componentFactories must be an object');
    this.testbed=testbed;
    this.components={};
    this.dependencies={broker:testbed.broker,market:testbed.market,clock:testbed.clock,ledger:testbed.ledger,rng:testbed.rng,trace:testbed.trace,components:this.components,...overrides};
    for(const [name,factory] of Object.entries(componentFactories)){
      if(typeof factory!=='function') throw new TypeError(`component factory ${name} must be a function`);
      this.components[name]=factory(this.dependencies);
    }
  }
  component(name){return this.components[name];}
  async invoke(componentName,method,input){
    const component=this.components[componentName];
    if(!component) throw new TypeError(`unknown component ${componentName}`);
    if(typeof component[method]!=='function') throw new TypeError(`${componentName} does not implement ${method}()`);
    this.testbed.trace.record('composition.invoke',{component:componentName,method,input});
    const output=await component[method](input);
    this.testbed.trace.record('composition.result',{component:componentName,method,output});
    return output;
  }
}

export async function runScenario({scenario,driver,invariants=DEFAULT_INVARIANTS,drain=true}){
  if(!scenario||typeof scenario!=='object') throw new TypeError('scenario is required');
  if(typeof driver!=='function') throw new TypeError('scenario driver must be a function');
  const t=createExecutionTestbed({
    startMs:scenario.startMs??0,seed:scenario.seed??1,funds:scenario.initial?.funds,
    positions:scenario.initial?.positions,orders:scenario.initial?.orders,trades:scenario.initial?.trades,
    brokerScripts:scenario.broker?.scripts??{},faultRules:scenario.broker?.faults??[]
  });
  for(const event of scenario.market??[]) t.market.scheduleQuote(event.atMs,event.instrument,event.quote);
  t.trace.record('scenario.start',{name:scenario.name,seed:scenario.seed??1});
  const result=await driver(t,scenario);
  if(drain) await t.clock.runUntilIdle();
  checkInvariants(t.trace.all(),invariants);
  t.trace.record('scenario.complete',{name:scenario.name});
  return {result,trace:t.trace.all(),testbed:t};
}

export async function runMassScenarios({count,startSeed=1,scenarioFactory,driver,invariants=DEFAULT_INVARIANTS}){
  if(!Number.isInteger(count)||count<1) throw new TypeError('count must be positive integer');
  if(typeof scenarioFactory!=='function') throw new TypeError('scenarioFactory must be a function');
  const summaries=[];
  for(let i=0;i<count;i++){
    const seed=startSeed+i;
    try{
      const scenario=await scenarioFactory(seed,new SeededRng(seed));
      const out=await runScenario({scenario:{...scenario,seed},driver,invariants});
      summaries.push({seed,ok:true,eventCount:out.trace.length});
    }catch(error){
      error.reproductionSeed=seed;
      error.reproductionScenario=await scenarioFactory(seed,new SeededRng(seed));
      throw error;
    }
  }
  return summaries;
}
