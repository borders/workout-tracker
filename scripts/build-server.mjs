import { cp, access, rm } from 'node:fs/promises';
await cp(new URL('../server/api/',import.meta.url),new URL('../dist/api/',import.meta.url),{recursive:true});

await cp(new URL('../server/gate.php',import.meta.url),new URL('../dist/gate.php',import.meta.url));

await cp(new URL('../server/mcp/',import.meta.url),new URL('../dist/mcp/',import.meta.url),{recursive:true});
await rm(new URL('../dist/vendor/',import.meta.url),{recursive:true,force:true});
try {
  await access(new URL('../vendor/autoload.php',import.meta.url));
} catch {
  console.warn('Optional MCP dependencies missing: run composer install --no-dev before building an MCP-enabled release. Website and Assistant REST remain available.');
  process.exit(0);
}
await cp(new URL('../vendor/',import.meta.url),new URL('../dist/vendor/',import.meta.url),{recursive:true});
