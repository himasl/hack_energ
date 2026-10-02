import { readFileSync } from 'node:fs';
import BpmnModdle from 'bpmn-moddle';

const moddle = new BpmnModdle();
const xml = readFileSync(0, 'utf-8');

try {
  const { warnings } = await moddle.fromXML(xml);
  console.log(JSON.stringify(warnings.map(w => w.message)));
} catch (e) {
  console.log(JSON.stringify([e.message]));
}
