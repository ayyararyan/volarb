function needMethod(value,name,method){
  if(!value || typeof value[method]!=='function') throw new TypeError(`${name} must implement ${method}()`);
  return value;
}
export function assertBrokerPort(value){ return needMethod(value,'brokerPort','call'); }
export function assertClockPort(value){
  needMethod(value,'clock','now');
  needMethod(value,'clock','schedule');
  return value;
}
export function assertLedgerPort(value){
  needMethod(value,'ledger','append');
  needMethod(value,'ledger','entries');
  return value;
}
export function assertMarketPort(value){ return needMethod(value,'market','snapshot'); }
