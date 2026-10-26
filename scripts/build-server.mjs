import { cp } from 'node:fs/promises';
await cp(new URL('../server/api/',import.meta.url),new URL('../dist/api/',import.meta.url),{recursive:true});
