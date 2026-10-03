export class SeededRng {
  constructor(seed=1){
    const n=Number(seed)>>>0;
    this.state=n||0x9e3779b9;
  }
  next(){
    let x=this.state;
    x^=x<<13;x^=x>>>17;x^=x<<5;
    this.state=x>>>0;
    return this.state/0x100000000;
  }
  int(min,max){
    if(!Number.isInteger(min)||!Number.isInteger(max)||max<min) throw new TypeError('invalid integer range');
    return min+Math.floor(this.next()*(max-min+1));
  }
  bool(probability=0.5){
    if(probability<0||probability>1) throw new TypeError('probability must be within [0,1]');
    return this.next()<probability;
  }
  pick(values){
    if(!Array.isArray(values)||!values.length) throw new TypeError('pick requires non-empty array');
    return values[this.int(0,values.length-1)];
  }
}
