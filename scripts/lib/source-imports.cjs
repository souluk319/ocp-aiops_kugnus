const parseNamedBindings = (clause) => clause
  .split(',')
  .map((entry) => entry.trim().replace(/^type\s+/, ''))
  .filter(Boolean)
  .map((entry) => {
    const [imported, local = imported] = entry.split(/\s+as\s+/);
    return { imported: imported.trim(), local: local.trim() };
  });

const ecmaScriptImports = (source) => {
  const imports = [];
  const importPattern = /^\s*import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"]\s*;?/gm;
  let match;

  while ((match = importPattern.exec(source)) !== null) {
    const clause = match[1].trim();
    const moduleSpecifier = match[2];
    const namedMatch = clause.match(/\{([\s\S]*?)\}/);
    const namespaceMatch = clause.match(/\*\s+as\s+([A-Za-z_$][\w$]*)/);
    const defaultMatch = clause.match(/^([A-Za-z_$][\w$]*)\s*(?:,|$)/);

    if (defaultMatch) {
      imports.push({ moduleSpecifier, imported: 'default', local: defaultMatch[1] });
    }
    if (namespaceMatch) {
      imports.push({ moduleSpecifier, imported: '*', local: namespaceMatch[1] });
    }
    if (namedMatch) {
      for (const binding of parseNamedBindings(namedMatch[1])) {
        imports.push({ moduleSpecifier, ...binding });
      }
    }
  }

  return imports;
};

const pythonImports = (source) => {
  const imports = [];
  const importPattern = /^\s*from\s+([.\w]+)\s+import\s+(?:\(([\s\S]*?)\)|([^\n]+))/gm;
  let match;

  while ((match = importPattern.exec(source)) !== null) {
    const moduleSpecifier = match[1];
    const clause = (match[2] ?? match[3]).replace(/#.*$/gm, '');
    for (const binding of parseNamedBindings(clause)) {
      imports.push({ moduleSpecifier, ...binding });
    }
  }

  return imports;
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
