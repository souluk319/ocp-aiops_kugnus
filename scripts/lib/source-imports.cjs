const { parse } = require('@babel/parser');
const { spawnSync } = require('child_process');

const ecmaScriptImports = (source) => {
  const imports = [];
  const program = parse(source, {
    sourceType: 'module',
    plugins: ['jsx', 'typescript'],
  }).program;

  for (const statement of program.body) {
    if (statement.type !== 'ImportDeclaration') continue;
    const moduleSpecifier = statement.source.value;
    for (const specifier of statement.specifiers) {
      if (specifier.type === 'ImportDefaultSpecifier') {
        imports.push({ moduleSpecifier, imported: 'default', local: specifier.local.name });
      } else if (specifier.type === 'ImportNamespaceSpecifier') {
        imports.push({ moduleSpecifier, imported: '*', local: specifier.local.name });
      } else if (specifier.type === 'ImportSpecifier') {
        const imported = specifier.imported.type === 'Identifier'
          ? specifier.imported.name
          : specifier.imported.value;
        imports.push({ moduleSpecifier, imported, local: specifier.local.name });
      }
    }
  }

  return imports;
};

const pythonImports = (source) => {
  const parser = [
    'import ast, json, sys',
    'tree = ast.parse(sys.stdin.read())',
    'items = []',
    'for node in tree.body:',
    '    if isinstance(node, ast.ImportFrom):',
    '        module = "." * node.level + (node.module or "")',
    '        for alias in node.names:',
    '            items.append({"moduleSpecifier": module, "imported": alias.name, "local": alias.asname or alias.name})',
    'print(json.dumps(items))',
  ].join('\n');
  const result = spawnSync('python3', ['-c', parser], {
    input: source,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    throw new Error(`Unable to parse Python imports:\n${result.stderr}`);
  }
  return JSON.parse(result.stdout);
};

const assertImport = (imports, expected, message) => {
  const found = imports.some((entry) => (
    entry.moduleSpecifier === expected.moduleSpecifier &&
    entry.imported === expected.imported &&
    entry.local === (expected.local ?? expected.imported)
  ));
  if (!found) {
    throw new Error(`${message}\n${JSON.stringify({ expected, imports }, null, 2)}`);
  }
};

const assertEcmaScriptImport = (source, expected, message) => {
  assertImport(ecmaScriptImports(source), expected, message);
};

const assertPythonImport = (source, expected, message) => {
  assertImport(pythonImports(source), expected, message);
};

module.exports = {
  assertEcmaScriptImport,
  assertPythonImport,
  ecmaScriptImports,
  pythonImports,
};

if (require.main === module) {
  const jsFixture = `
    // import { Fake } from './commented';
    const embedded = "import { Fake } from './string'";
    import Real, { type Shape, value as localValue } from './real';
  `;
  const pythonFixture = `
# from .commented import Fake
embedded = "from .string import Fake"
from .real import Shape, value as local_value
  `;
  const jsImports = ecmaScriptImports(jsFixture);
  const pyImports = pythonImports(pythonFixture);
  if (jsImports.some((entry) => entry.moduleSpecifier !== './real')) {
    throw new Error('ECMAScript parser accepted a dead import');
  }
  if (pyImports.some((entry) => entry.moduleSpecifier !== '.real')) {
    throw new Error('Python parser accepted a dead import');
  }
  console.log('source import parser PASS');
}
